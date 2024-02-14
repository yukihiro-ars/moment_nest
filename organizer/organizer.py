
import os
import questionary
import glob

from exif import Image

TARGET_EXT = ['mp4', 'mov', 'jpeg', 'jpg', 'png', 'gif']
MSG_SELECT_PATH_1 = '整理対象のフォルダを選択してください'
MSG_SELECT_PATH_2 = 'フォルダ指定が不正です\nフォルダを再選択してください'


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

        # ファイル全量の把握
        for ext in dict_ext.keys():
            length = len(dict_ext[ext])
            if ext in TARGET_EXT:
                print(f'target ext = {ext}, len = {length}')
                # Backupフォルダに退避してから処理開始(ファイルごとに実施する想定)
                # 画像の場合、EXIF、動画の場合は日付情報を取得して新規ファイル名の作成
                # 動画向けライブラリの検討 https://github.com/kkroening/ffmpeg-python
                for file in dict_ext[ext]:
                    # TODO base_path末尾にスラッシュ指定された場合の対策検討
                    # https://gitlab.com/TNThieding/exif/-/issues/51
                    file_path = f'{base_path}\\{file}'
                    with open(file_path, 'rb') as file_stream:
                        print(file)
                        image_desc = Image(file_stream)
                        if image_desc.has_exif:
                            if hasattr(image_desc, 'datetime_original'):
                                print(image_desc.datetime_original)
                            elif hasattr(image_desc, 'datetime'):
                                print(image_desc.datetime)
                            elif hasattr(image_desc, 'datetime_digitized'):
                                print(image_desc.datetime_digitized)
                            else:
                                print('has no datetime')
                        else:
                            print('has no exif')
                # フォルダ存在チェック＆フォルダ作成
                # 画像コピー＆リネーム
                # https://python-academia.com/file-transfer/
                # https://qiita.com/kuroitu/items/f18acf87269f4267e8c1#%E8%87%AA%E5%88%86%E3%81%A7%E4%BD%9C%E3%81%A3%E3%81%A6%E3%81%BF%E3%82%8B
                # 完了後Backupフォルダの対象ファイルを削除(ファイルごとに実施する想定)
            else:
                print(f'no target ext = {ext}, len = {length}')
                # 対象外ファイルの退避処理
    except Exception as e:
        print(e)
    finally:
        print('organizer処理完了')
