
import os
import questionary
import glob
from pprint import pprint
from datetime import datetime
from tqdm import tqdm
from exif import Image

TARGET_EXT = ['mp4', 'mov', 'jpeg', 'jpg', 'png', 'gif']
HAS_EXIF_EXT = ['jpeg', 'jpg']
MSG_SELECT_PATH_1 = '整理対象のフォルダを選択してください'
MSG_SELECT_PATH_2 = 'フォルダ指定が不正です\nフォルダを再選択してください'
DATETIME_EXIF_KEY = ['datetime_original', 'datetime', 'datetime_digitized']


def do_organize():
    try:
        base_path = None
        isfirst = True
        while base_path is None or os.path.isdir(base_path) is False:
            msg = MSG_SELECT_PATH_1 if isfirst else MSG_SELECT_PATH_2
            base_path = questionary.text(msg).ask()
            print(base_path)
            isfirst = False
            # TODO ずっとDir判定されない場合の救済処置は検討

        # 指定フォルダ配下のファイル一覧を取得
        files = glob.glob('**/*.*', root_dir=base_path, recursive=True)

        dict_ext = {}
        # 拡張子ごとに分類
        for file in files:
            # 拡張子取得(小文字統一)
            ext = file.rsplit('.', 1)[1].lower()
            # 拡張子ごとに分類
            if ext not in dict_ext:
                dict_ext[ext] = []
            dict_ext[ext].append(file)

        # 拡張子単位で処理
        dict_out = {}
        for ext in dict_ext.keys():
            length = len(dict_ext[ext])
            # 対象拡張子に絞って処理続行
            if ext in TARGET_EXT:
                # TODO 余裕が出てきたらプログレスバーはtqdmをやめて自前で作ることも検討
                with tqdm(total=length, desc=ext) as pbar:
                    for file in dict_ext[ext]:
                        pbar.update(1)
                        dt = None
                        # TODO base_path末尾にスラッシュ指定された場合の対策検討
                        # https://gitlab.com/TNThieding/exif/-/issues/51
                        # TODO デコレータどっかで使えないかな
                        # https://qiita.com/mtb_beta/items/d257519b018b8cd0cc2e
                        file_path = f'{base_path}\\{file}'
                        # https://docs.python.org/ja/3/library/stat.html
                        file_stat = os.stat(file_path)
                        # 新名称フォーマット関数
                        def new_f(p_dt): \
                            return f'{p_dt}_{file_stat.st_size}.{ext}'
                        # exifの日付情報を取得(jpgのみ)
                        if ext in HAS_EXIF_EXT:
                            with open(file_path, 'rb') as file_stream:
                                image_desc = Image(file_stream)
                                if image_desc.has_exif:
                                    dt = get_attr_if_exists_props(
                                        image_desc, DATETIME_EXIF_KEY)
                        # exifから日付情報が取得できない場合は、ファイルの更新日時より取得
                        if dt is None:
                            dt = file_stat.st_mtime
                        # 日付情報が取得できた場合
                        if dt is not None:
                            dt_dt = conv_datetime(dt)
                            try:
                                apply_file_part_by_file_new_old(
                                    get_dict_dir_part_by_dt(dict_out, dt_dt),
                                    new_f(dt_dt.strftime('%Y%m%d_%H%M%S')),
                                    file_path)
                            except Exception as e:
                                raise Exception(
                                    f'has error {file_path}.{e}')
                        else:
                            print(f'is datetime none {file}')

                    # 関数判定 callable(func) = True
                    # TODO フォルダコピー移動関連　仕様から検討
                    # datetime型オブジェクトより、年月のフォルダ名と%Y%m%d_%H%M%S_filesize.extのファイル名を作成
                    # 変換後のファイル名と旧ファイル名（同じファイル名の存在を考慮し、listで保持）のマップを作成
                    # 終端処理実施(画像コピー＆リネーム等)
                    # Backupフォルダに退避してから処理開始(ファイルごとに実施する想定)
                    # https://python-academia.com/file-transfer/
                    # https://qiita.com/kuroitu/items/f18acf87269f4267e8c1#%E8%87%AA%E5%88%86%E3%81%A7%E4%BD%9C%E3%81%A3%E3%81%A6%E3%81%BF%E3%82%8B
                    # 完了後Backupフォルダの対象ファイルを削除(ファイルごとに実施する想定)
            else:
                # 対象外ファイルの退避処理
                print(f'no target ext = {ext}, len = {length}')
        # pprint(dict_out)
        for k1 in dict_out.keys():
            for k2 in dict_out[k1].keys():
                for k3 in dict_out[k1][k2].keys():
                    old_len = len(dict_out[k1][k2][k3])
                    if 1 < old_len:
                        print(dict_out[k1][k2][k3])
        print('success.')
    except Exception as e:
        print(e)
        print('error.')
    finally:
        print('the process has completed.')


def conv_datetime(dt):
    if isinstance(dt, str):
        return datetime.strptime(dt, '%Y:%m:%d %H:%M:%S')
    elif isinstance(dt, float):
        return datetime.fromtimestamp(dt)
    else:
        raise Exception('Unexpected dt type. at conv_datetime')


def get_dict_dir_part_by_dt(dict_out, dt_dt):
    try:
        ym = dt_dt.strftime('%Y%m')
        y = dt_dt.strftime('%Y')
        if y not in dict_out:
            dict_out[y] = {}
        if ym not in dict_out[y]:
            dict_out[y][ym] = {}
        return dict_out[y][ym]
    except Exception as e:
        raise Exception(f'{e}. at get_dict_dir_part_by_dt')


def apply_file_part_by_file_new_old(dict_dir, new, old):
    try:
        if new not in dict_dir:
            dict_dir[new] = []
        dict_dir[new].append(old)
    except Exception as e:
        raise Exception(f'{e}. apply_file_part_by_file_new_old')


def get_attr_if_exists_props(item, props):
    try:
        for attr in props:
            if hasattr(item, attr):
                return getattr(item, attr)
        return None
    except Exception as e:
        raise Exception(f'{e}. get_attr_if_exists_props')
