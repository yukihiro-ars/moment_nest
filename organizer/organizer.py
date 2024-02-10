
import os
import questionary
import glob

TARGET_EXT = ['mp4', 'mov', 'jpeg', 'jpg', 'png', 'gif']
MSG_SELECT_PATH_1 = '整理対象のフォルダを選択してください'
MSG_SELECT_PATH_2 = 'フォルダ指定が不正です\nフォルダを再選択してください'


def do_organize():
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
            # フォルダ存在チェック＆フォルダ作成
            # 画像コピー＆リネーム
            # 完了後Backupフォルダの対象ファイルを削除(ファイルごとに実施する想定)
        else:
            print(f'no target ext = {ext}, len = {length}')
            # 対象外ファイルの退避処理

        for file in dict_ext[ext]:
            print(f'\t{file}')

