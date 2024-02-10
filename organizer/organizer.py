
import os
import questionary
import glob

TARGET_EXT = ['mp4', 'jpeg', 'jpg', 'png', 'gif']
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
    files = glob.glob('*.*', root_dir=base_path, recursive=True)
    for file in files:
        print(file)

    # ■処理内容検討
    # 画像・動画ファイルとそうでないファイルの仕分け
    # ファイル全量の把握
    # Backupフォルダに退避してから処理開始(ファイルごとに実施する想定)
    # 画像の場合、EXIF、動画の場合は日付情報を取得して新規ファイル名の作成
    # フォルダ存在チェック＆フォルダ作成
    # 画像コピー＆リネーム
    # 完了後Backupフォルダの対象ファイルを削除(ファイルごとに実施する想定)
