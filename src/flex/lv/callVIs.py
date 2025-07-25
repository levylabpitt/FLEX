import win32com.client
import os
import subprocess

lv_dir = os.path.dirname(os.path.abspath(__file__))
callTransportdir = lv_dir + "\\callTransport.vi"
callVNAVI = lv_dir + "\\callVNA.vi"
getCEExpPathVI = lv_dir + "\\getCE_ExpPath.vi"

def callTransport(VI="", exp_folder="", comments="", tdms_params=""):
    if VI == "":
        raise Exception("Please specify a VI to run.")
    command = rf'g-cli --lv-ver 2019 {callTransportdir} -- "{VI}" "{exp_folder}" "{comments}" "{tdms_params}"'
    os.system(command)

def callVNA(exp_folder="", comments="", tdms_params=""):
    command = rf'g-cli --lv-ver 2019 {callVNAVI} -- "{exp_folder}" "{comments}" "{tdms_params}"'
    os.system(command)

def getExpPath():
    command = rf'g-cli --lv-ver 2019 {getCEExpPathVI}'
    result = subprocess.run(command, capture_output=True, text=True)
    return result.stdout.rstrip('\n'), result.stdout.rstrip('\n').partition('Nextcloud')[2]

if __name__ == "__main__":
    callTransport(exp_folder="test1", tdms_params={"test":124}, VI="Lockin_sweep", comments='Test comment')
    # callVNA(exp_folder="test", comments='testing', tdms_params=5)
    # print(getExpPath()[0])

