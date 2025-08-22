import sys
import os
import inspect
import clr # install pythonnet instead of clr
import numpy as np

strPathDllFolder = os.environ.get("ProgramFiles") + "\\New Focus\\New Focus Picomotor Application\\Bin" 

sys.path.append(strPathDllFolder)
clr.AddReference("UsbDllWrap")

from Newport.USBComm import *
from System.Text import StringBuilder
from System.Collections import Hashtable
from System.Collections import IDictionaryEnumerator

# Call the class constructor to create an object
oUSB = USB(True)

# Discover all connected devices
bStatus = oUSB.OpenDevices(0, True)

if bStatus:
    oDeviceTable = oUSB.GetDeviceTable()
    nDeviceCount = oDeviceTable.Count
    print("Device Count = %d" % nDeviceCount)

    # If no devices were discovered
    if (nDeviceCount == 0) :
        print ("No discovered devices.\n")
    else :
        oEnumerator = oDeviceTable.GetEnumerator ()
        strDeviceKeyList = np.array ([])

        # Iterate through the Device Table creating a list of Device Keys
        for nIdx in range (0, nDeviceCount) :
            if (oEnumerator.MoveNext ()) :
                strDeviceKeyList = np.append (strDeviceKeyList, oEnumerator.Key)

        print (strDeviceKeyList)
        print ("\n")

        strBldr = StringBuilder (64)

        # Iterate through the list of Device Keys and query each device with *IDN?
        for oDeviceKey in strDeviceKeyList :
            strDeviceKey = str (oDeviceKey)
            print (strDeviceKey)
            strBldr.Remove (0, strBldr.Length)
            nReturn = oUSB.Query (strDeviceKey, "*IDN?", strBldr)
            print ("Return Status = %d" % nReturn)
            print ("*IDN Response = %s\n" % strBldr.ToString ())
else :
    print ("\n***** Error:  Could not open the devices. *****\n\nCheck the log file for details.\n")

# Shut down all communication
oUSB.CloseDevices ()
print ("Devices Closed.\n")
