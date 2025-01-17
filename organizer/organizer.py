import os
import questionary
import glob
import shutil
from enum import Enum
from datetime import datetime
from tqdm import tqdm
from exif import Image

TARGET_EXT = ['mp4', 'mov', 'jpeg', 'jpg', 'png', 'gif']
HAS_EXIF_EXT = ['jpeg', 'jpg']
MSG_SELECT_PATH_1 = '整理対象のフォルダを選択してください'
MSG_SELECT_PATH_2 = 'フォルダ指定が不正です\nフォルダを再選択してください'
MSG_SHOW_PLAN = '整理計画を確認しますか？'
MSG_EXEC_PLAN = '整理計画を実行しますか？'
DATETIME_EXIF_KEY = ['datetime_original', 'datetime', 'datetime_digitized']


class PlaneMode(Enum):
    SHOW = 1
    EXEC = 2
    SAFE_EXEC = 3


def do_organize():
    """ベースディレクトリを取得し、ファイルのスキャン、整理計画の表示および実行を行うエントリーポイント関数。"""
    try:
        base_dir = None
        is_first = True

        # ベースディレクトリ取得
        while base_dir is None or not os.path.isdir(base_dir):
            msg = MSG_SELECT_PATH_1 if is_first else MSG_SELECT_PATH_2
            base_dir = questionary.path(msg).ask()
            print(base_dir)
            is_first = False
            # TODO 不正上限チェック

        dict_ext = scan(base_dir)

        # フルパス形式の関数を定義
        def full_f(relative_path): return f'{base_dir}\\{relative_path}'

        dict_plan = planning(dict_ext, full_f)

        # 整理計画確認
        if questionary.confirm(MSG_SHOW_PLAN).ask():
            do_plan(PlaneMode.SHOW, dict_plan, full_f)

        # 整理計画実行
        if questionary.confirm(MSG_EXEC_PLAN).ask():
            do_plan(PlaneMode.EXEC, dict_plan, full_f)

        print('success.')
    except Exception as e:
        print(f'error. e={e}')
    finally:
        print('the process has completed.')


def scan(base_dir):
    """ベースディレクトリをスキャンし、拡張子単位でファイルを分類する。"""
    files = glob.glob('**/*.*', root_dir=base_dir, recursive=True)
    dict_ext = {}

    for file in files:
        ext = file.rsplit('.', 1)[1].lower()
        dict_ext.setdefault(ext, []).append(file)

    return dict_ext


def planning(dict_ext, full_f):
    """スキャン結果の辞書から整理計画を取得する。"""
    dict_plan = {}

    for ext, files in dict_ext.items():
        if ext not in TARGET_EXT:
            print(f'no target ext = {ext}, len = {len(files)}')
            continue

        with tqdm(total=len(files), desc=ext) as pbar:
            for relative_path in files:
                pbar.update(1)
                full_path = full_f(relative_path)
                dt = get_datetime(full_path, ext)

                if dt:
                    dt_dt = conv_datetime(dt)
                    try:
                        apply_file_part_by_file_new_old(
                            get_dict_dir_part_by_dt(dict_plan, dt_dt),
                            new_f_name(full_path, dt_dt, ext),
                            relative_path
                        )
                    except Exception as e:
                        raise Exception(f'Error processing {full_path}: {e}')
                else:
                    print(f'is datetime none {full_path}')

    return dict_plan


def get_datetime(full_path, ext):
    """ファイルのEXIF情報または更新日時から日付情報を取得する。"""
    file_stat = os.stat(full_path)

    if ext in HAS_EXIF_EXT:
        with open(full_path, 'rb') as file_stream:
            image_desc = Image(file_stream)
            if image_desc.has_exif:
                return get_attr_if_exists_props(image_desc, DATETIME_EXIF_KEY)

    return file_stat.st_mtime


def new_f_name(full_path, dt_dt, ext):
    """新しいファイル名を生成する。"""
    file_stat = os.stat(full_path)
    return f'{dt_dt.strftime("%Y%m%d_%H%M%S")}_{file_stat.st_size}.{ext}'


def conv_datetime(dt):
    """日付オブジェクトをdatetime型に変換する。"""
    if isinstance(dt, str):
        return datetime.strptime(dt, '%Y:%m:%d %H:%M:%S')
    elif isinstance(dt, float):
        return datetime.fromtimestamp(dt)
    else:
        raise ValueError('Unexpected dt type in conv_datetime')


def get_dict_dir_part_by_dt(dict_plan, dt_dt):
    """整理計画の辞書に日付情報を基にした要素を追加し、返却する。"""
    ym = dt_dt.strftime('%Y%m')
    y = dt_dt.strftime('%Y')
    dict_plan.setdefault(y, {}).setdefault(ym, {})
    return dict_plan[y][ym]


def apply_file_part_by_file_new_old(dict_dir, new, old):
    """新ファイル名と旧ファイル名を整理計画の辞書に適用する。"""
    dict_dir.setdefault(new, []).append(old)


def get_attr_if_exists_props(item, props):
    """アイテムに指定プロパティが存在する場合、その値を返却する。"""
    for attr in props:
        if hasattr(item, attr):
            return getattr(item, attr)
    return None


def do_plan(mode, dict_plan, full_f):
    """整理計画を表示および実行する。"""
    try:
        cnt = 0
        bk_cnt = 0

        for d1, d1_val in dict_plan.items():
            abs_d1 = full_f(d1)
            mkdir_is_no_exist(abs_d1)

            for d2, d2_val in d1_val.items():
                abs_d2 = os.path.join(abs_d1, d2)
                mkdir_is_no_exist(abs_d2)

                for new, olds in d2_val.items():
                    cnt += 1
                    full_old = full_f(olds[0])
                    full_new = os.path.join(abs_d2, new)

                    print(f'cp {full_old} => {full_new}')
                    if mode == PlaneMode.EXEC:
                        shutil.move(src=full_old, dst=full_new)

                    # 同一データのbackup
                    if len(olds) > 1:
                        for old in olds[1:]:
                            bk_cnt += 1
                            full_bk_src = full_f(old)
                            full_bk_dst = os.path.join(abs_d2, 'bk', old)
                            print(f'backup {full_bk_src} => {full_bk_dst}')
                            if mode == PlaneMode.EXEC:
                                mkdir_is_no_exist(full_bk_dst)
                                shutil.move(src=full_bk_src, dst=full_bk_dst)

        print(f'new count = {cnt}')
        print(f'bk count = {bk_cnt}')

        # if mode == PlaneMode.EXEC:
        # clean_empty_dirs(full_f(''))
    except Exception as e:
        raise Exception(f'Error in do_plan: {e}')


def mkdir_is_no_exist(dir):
    if not os.path.isdir(dir):
        os.makedirs(dir)


def clean_empty_dirs(base_dir):
    """空のディレクトリを削除する。"""
    for dirpath, dirnames, filenames in os.walk(base_dir, topdown=False):
        if not dirnames and not filenames:
            os.rmdir(dirpath)
