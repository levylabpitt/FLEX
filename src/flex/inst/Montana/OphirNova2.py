import win32gui
import win32com.client
import time
import traceback

class OphirNova2:
    def __init__(self, serial_number=None):
        self.serial_number = serial_number
        self.OphirCOM = None
        self.serial = self.list_devices()[0]
        self.DeviceHandle = self.connect(self.serial)

    def list_devices(self):
        try:
            self.OphirCOM = win32com.client.Dispatch("OphirLMMeasurement.CoLMMeasurement")
            # Stop & Close all devices
            self.OphirCOM.StopAllStreams()
            self.OphirCOM.CloseAll()
            # Scan for connected Devices
            DeviceList = self.OphirCOM.ScanUSB()
            return DeviceList
        except OSError as err:
            print("OS error: {0}".format(err))
        except:
            traceback.print_exc()

    def connect(self, serial_number=None):
        if serial_number is None:
            serial_number = self.serial
        try:
            DeviceHandle = self.OphirCOM.OpenUSBDevice(serial_number)  # open first device
            exists = self.OphirCOM.IsSensorExists(DeviceHandle, 0)
            if exists:
                ranges = self.OphirCOM.GetRanges(DeviceHandle, 0)
                print(f'Connected to Device {serial_number} with ranges: {ranges}')
                return DeviceHandle
            else:
                print('\nNo Sensor attached to {0} !!!'.format(serial_number))
        except OSError as err:
            print("OS error: {0}".format(err))
        except:
            traceback.print_exc()
    
    def read_power(self):
        self.OphirCOM.StartStream(self.DeviceHandle, 0)
        time.sleep(.2)
        self.OphirCOM.StopAllStreams()
        data = self.OphirCOM.GetData(self.DeviceHandle, 0)
        power = data[0][-1]
        return power

    def disconnect(self):
        if self.OphirCOM:
            # Stop & Close all devices
            self.OphirCOM.StopAllStreams()
            self.OphirCOM.CloseAll()
            # Release the object
            self.OphirCOM = None

# Test
if __name__ == '__main__':
    ophir_nova2 = OphirNova2()
    ophir_nova2.read_power()
    ophir_nova2.disconnect()
