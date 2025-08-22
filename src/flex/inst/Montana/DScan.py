import ctypes
import os

class DScan:
    library_name = "C:\\Program Files\\Sphere Ultrafast Photonics S.A\\dscan-library\\bin\\dscan-library.dll"

    _lib = ctypes.cdll.LoadLibrary(os.path.join(os.path.dirname(os.path.realpath(__file__)), library_name))

    def __init__(self, serial_number: str):
        self._handle = self._lib.dscan_INVALID_HANDLE()
        handle = ctypes.c_uint32()
        status = self._lib.dscan_Create(serial_number.encode('utf-8'), ctypes.byref(handle))
        self._throw(status)
        self._handle = handle.value
        self.connect()

    def __del__(self):
        if self._handle != self._lib.dscan_INVALID_HANDLE():
            status = self._lib.dscan_Destroy(self._handle)
            self._handle = self._lib.dscan_INVALID_HANDLE()
            self._throw(status)

    def connect(self):
        status = self._lib.dscan_Connect(self._handle)
        self._throw(status)

    def disconnect(self):
        status = self._lib.dscan_Disconnect(self._handle)
        self._throw(status)

    def is_connected(self) -> bool:
        return self._lib.dscan_IsConnected(self._handle)

    def get_full_insertion_range(self) -> tuple[float, float]:
        start_mm = ctypes.c_double()
        stop_mm = ctypes.c_double()
        status = self._lib.dscanComp_GetFullInsertionRange(self._handle, ctypes.byref(start_mm), ctypes.byref(stop_mm))
        self._throw(status)
        return (start_mm.value, stop_mm.value)
    
    def get_insertion(self) -> float:
        insertion_mm = ctypes.c_double()
        status = self._lib.dscanComp_GetInsertion(self._handle, ctypes.byref(insertion_mm))
        self._throw(status)
        return round(insertion_mm.value, 3)

    def set_insertion(self, insertion_mm: float):
        status = self._lib.dscanComp_SetInsertion(self._handle, ctypes.c_double(insertion_mm))
        self._throw(status)

    def _throw(self, status):
        if not status:
            return
        
        message = ctypes.create_string_buffer(self._lib.dscan_ERROR_MESSAGE_BUFFER_LEN())
        self._lib.dscan_GetLastStatusMessage(message, self._lib.dscan_ERROR_MESSAGE_BUFFER_LEN())
        message = message.value.decode('ascii').strip()

        raise Exception(message)
