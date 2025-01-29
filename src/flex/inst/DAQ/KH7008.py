'''
Levylab FLEX instrument driver for Krohn-Hite 7008.
<https://github.com/levylabpitt/Krohn-Hite-7008>

Authors: 
Pubudu Wijesinghe <pubudu.wijesinghe@levylab.org>
Aria Hajikhani <aria.hajikhani@levylab.org>

Contact an author for any queries.
'''

from flex.inst.base import Instrument
import time
import os

_DEFAULT_ADDRESS = 'tcp://localhost:29160'

logpath = os.path.join(os.environ.get('LOCALAPPDATA'), 'Levylab', 'FLEX', 'logs')
os.makedirs(logpath, exist_ok=True)

class KH7008(Instrument):
    def __init__(self, address= _DEFAULT_ADDRESS):
        super().__init__(address, log_file= logpath + '\instrument.log')
    
    def get_allowed_values(cls):
        """
        Provides a dictionary of valid values for each configurable parameter ("channel", "gain", "input", "shunt", "couple", "filter") in the Krohn-Hite amplifier.
        
        Example (getting allowed values for all parameters):
            >>> print(kh.get_allowed_values())

        Example (getting allowed values for one parameter (for example "gain")):
            >>> print(kh.get_allowed_values()["gain"])
        """

        return {
            "channel": [1, 2, 3, 4, 5, 6, 7, 8],
            "gain": [1, 10, 100, 1000],
            "input": ["OFF", "SE+", "SE-", "DIFF"],
            "shunt": [0, 50, 500, 5000, 50000, 10000000],
            "couple": ["AC", "DC"],
            "filter": ["OFF", "ON"]
        }
    
    def set_all_channels(self, channels_config: list[dict]):
        """
        Apply configurations for multiple channels of the Krohn-Hite amplifier at once. 
        Users must define the configurations for the each channel in the required format, mentioned below:

        Args: 
            channels_config(list[dict]): A list of dictionaries, where each dictionary defines the settings for one channel. Each dictionary must include:
                - "channel" (int): The channel number (valid: 1-8).
                - "gain" (int): Amplifier gain (valid: 1, 10, 100, 1000).
                - "input" (str): Input configuration (valid: "OFF", "SE+", "SE-", "DIFF").
                - "shunt" (int): Shunt resistance in ohms (valid: 0, 50, 500, 5000, 50000, 10000000).
                - "couple" (str): Input coupling mode (valid: "AC", "DC").
                - "filter" (str): Low-pass filter status (valid: "OFF", "ON").

        Raises:
            ValueError: If any parameter in the provided configurations is not within the allowed values.

        Returns:
            dict or None: The response from the instrument, typically indicating success or an error message if the command fails.

        Example (configuring two channels 1, and 2):
        >>> channels_config = [
        ...     {"channel": 1, "gain": 10, "input": "SE+", "shunt": 500, "couple": "AC", "filter": "ON"},
        ...     {"channel": 2, "gain": 100, "input": "DIFF", "shunt": 50, "couple": "DC", "filter": "OFF"}
        ... ]
        >>> result = kh.set_all_channels(channels_config)
        >>> print(result)
        """

        allowed_values = self.get_allowed_values()
        for ch_config in channels_config:
            if ch_config["channel"] not in allowed_values["channel"]:
                raise ValueError(f"Invalid channel: {ch_config['channel']}. Allowed values for channel: {allowed_values['channel']}")
            if ch_config["gain"] not in allowed_values["gain"]:
                raise ValueError(f"Invalid gain: {ch_config['gain']}. Allowed values for gain: {allowed_values['gain']}")
            if ch_config["input"] not in allowed_values["input"]:
                raise ValueError(f"Invalid input: {ch_config['input']}. Allowed values for input: {allowed_values['input']}")
            if ch_config["couple"] not in allowed_values["couple"]:
                raise ValueError(f"Invalid couple: {ch_config['couple']}. Allowed values for couple: {allowed_values['couple']}")
            if ch_config["filter"] not in allowed_values["filter"]:
                raise ValueError(f"Invalid filter: {ch_config['filter']}. Allowed values for filter: {allowed_values['filter']}")
            
        cmd = 'setAllChannels'
        params = {'params': channels_config}
        response = self._send_command(cmd, params)
        return response.get('result')
    
    def get_all_channels(self):
        """
        Retrieve and return the current settings for all channels of the Krohn-Hite amplifier.
        The response contains each channel's configuration, including: "gain", "input" mode, "shunt" resistance, "couple" mode, and "filter" status.

        Returns:
            list[dict]: A list of dictionaries, where each dictionary represents the configuration of one channel. Each dictionary contains:
                - "channel" (int): The channel number (1-8).
                - "gain" (int): The current amplifier gain.
                - "input" (str): The current input configuration.
                - "shunt" (int): The current shunt resistance in ohms.
                - "couple" (str): The current input coupling mode.
                - "filter" (str): The current low-pass filter status.
            `None`: The communication with the instrument fails.

        Example:
        >>> print(kh.get_all_channels())
        [
            {"channel": 1, "gain": 10, "input": "SE+", "shunt": 500, "couple": "AC", "filter": "ON"},
            {"channel": 2, "gain": 100, "input": "DIFF", "shunt": 50, "couple": "DC", "filter": "OFF"},
            ...
        ]
        """
        cmd = 'getAllChannels'
        response = self._send_command(cmd)
        return response.get('result')
    
    def set_channel(self, channel_config: dict):
        """
        Apply configurations for a single channel of the Krohn-Hite amplifier. 
        Users must define the configurations for the specific channel in the required format, mentioned below:

        Args: 
            channel_config(dict): A dictionary specifying the setting for one channel. The dictionary must include:
                - "channel" (int): The channel number (valid: 1-8).
                - "gain" (int): Amplifier gain (valid: 1, 10, 100, 1000).
                - "input" (str): Input configuration (valid: "OFF", "SE+", "SE-", "DIFF").
                - "shunt" (int): Shunt resistance in ohms (valid: 0, 50, 500, 5000, 50000, 10000000).
                - "couple" (str): Input coupling mode (valid: "AC", "DC").
                - "filter" (str): Low-pass filter status (valid: "OFF", "ON").

        Raises:
            ValueError: If any parameter in the provided configuration is not within the allowed values.

        Returns:
             dict or None: The response from the instrument, typically indicating success or containing an error message if the command fails.

        Example (configuring channel 1):
        >>> channel_config = {
        ...     "channel": 1, "gain": 10, "input": "SE+", "shunt": 500, "couple": "AC", "filter": "ON"}
        ... }
        >>> result = kh.set_channel(channel_config)
        >>> print(result)
        """

        allowed_values = self.get_allowed_values()
        for ch_config in channel_config:
            if ch_config["channel"] not in allowed_values["channel"]:
                raise ValueError(f"Invalid channel: {ch_config['channel']}. Allowed values for channel: {allowed_values['channel']}")
            if ch_config["gain"] not in allowed_values["gain"]:
                raise ValueError(f"Invalid gain: {ch_config['gain']}. Allowed values for gain: {allowed_values['gain']}")
            if ch_config["input"] not in allowed_values["input"]:
                raise ValueError(f"Invalid input: {ch_config['input']}. Allowed values for input: {allowed_values['input']}")
            if ch_config["couple"] not in allowed_values["couple"]:
                raise ValueError(f"Invalid couple: {ch_config['couple']}. Allowed values for couple: {allowed_values['couple']}")
            if ch_config["filter"] not in allowed_values["filter"]:
                raise ValueError(f"Invalid filter: {ch_config['filter']}. Allowed values for filter: {allowed_values['filter']}")

        cmd = 'setChannel'
        params = {'params': channel_config}
        response = self._send_command(cmd, params)
        return response.get('result')
    
    def get_channel(self, channel):
        """
        Retrieve and return the current settings for a single channel of the Krohn-Hite amplifier.
        The response contains the specific channel's configuration, including: "gain", "input" mode, "shunt" resistance, "couple" mode, and "filter" status.

        Arg:
            channel (int): The channel number to retrieve (valid: 1-8)

        Returns:
            dict: A dictionary representing the configuration of the channel. The dictionary contains:
                - "channel" (int): The channel number (1-8).
                - "gain" (int): The current amplifier gain.
                - "input" (str): The current input configuration.
                - "shunt" (int): The current shunt resistance in ohms.
                - "couple" (str): The current input coupling mode.
                - "filter" (str): The current low-pass filter status.
            `None`: The communication with the instrument fails.

        Example (getting the configuration of channel 1):
        >>> print(kh.get_channel(channel = 1))
        {"channel": 1, "gain": 10, "input": "SE+", "shunt": 500, "couple": "AC", "filter": "ON"}
        """
        cmd = 'getChannel'
        params = {'channel': channel}
        response = self._send_command(cmd, params)
        return response.get('result')
    
if __name__ == "__main__":
    # Test the KH7008 class
    kh = KH7008("tcp://localhost:29160",)
    channels_config = [
        {
            'channel': 2,
            'gain': 10,
            'input': 'OFF',
            'shunt': 5,
            'couple': "DC",
            'filter': "OFF"
        }
    ]
    kh.set_all_channels(channels_config)
    print(kh.get_allowed_values())
    print(kh.get_allowed_values()["gain"])
    print(kh.get_channel(channel = 2))
    kh.close()