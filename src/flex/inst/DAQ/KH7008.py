'''
Levylab FLEX instrument driver for Krohn-Hite 7008.
<https://github.com/levylabpitt/Krohn-Hite-7008>

Authors: 
Pubudu Wijesinghe <pubudu.wijesinghe@levylab.org>
Aria Hajikhani <aria.hajikhani@levylab.org>

Contact an author for any queries.
'''

from flex.inst.base import Instrument
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
    
    def setAllChannels(self, channels_config: list[dict]):
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
        >>> result = kh.setAllChannels(channels_config)
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
    
    def getAllChannels(self):
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
        >>> print(kh.getAllChannels())
        [
            {"channel": 1, "gain": 10, "input": "SE+", "shunt": 500, "couple": "AC", "filter": "ON"},
            {"channel": 2, "gain": 100, "input": "DIFF", "shunt": 50, "couple": "DC", "filter": "OFF"},
            ...
        ]
        """
        cmd = 'getAllChannels'
        response = self._send_command(cmd)
        return response.get('result')
    


    def setChannel(self, channel_config: dict = None, channel: int = None, gain: int = None, 
                input: str = None, shunt: int = None, couple: str = None, filter: str = None):
        """
        Apply configurations for a single channel of the Krohn-Hite amplifier. 

        Users can either:
            - Provide all parameters individually. So arguments in this case are:
            Args:
                * channel (int): The channel number (1-8).
                * gain (int): Amplifier gain (1, 10, 100, 1000).
                * input (str): Input configuration ("OFF", "SE+", "SE-", "DIFF").
                * shunt (int): Shunt resistance (0, 50, 500, 5000, 50000, 10000000).
                * couple (str): Input coupling ("AC", "DC").
                * filter (str): Low-pass filter ("OFF", "ON").

            - Pass a `channel_config` dictionary containing the configuration. So arguments in this case are:
            Args:
                * channel_config (dict, optional): A dictionary with channel settings. Must include:
                    - "channel" (int): Channel number (1-8).
                    - "gain" (int): Amplifier gain (1, 10, 100, 1000).
                    - "input" (str): Input configuration ("OFF", "SE+", "SE-", "DIFF").
                    - "shunt" (int): Shunt resistance (0, 50, 500, 5000, 50000, 10000000).
                    - "couple" (str): Input coupling ("AC", "DC").
                    - "filter" (str): Low-pass filter ("OFF", "ON").
                    
        Raises:
            ValueError: If any parameter is invalid.

        Returns:
            dict or None: The response from the instrument.

        Example (Using a channel_config dictionary):
                >>> channel_config = {
                ...     "channel": 1, "gain": 10, "input": "SE+", "shunt": 500, "couple": "AC", "filter": "ON"
                ... }
                >>> result = kh.setChannel(channel_config)
                >>> print(result)

        Example (Using individual parameters):
                >>> result = kh.setChannel(channel=1, gain=10, input="SE+", shunt=500, couple="AC", filter="ON")
                >>> print(result)
        """

        allowed_values = self.get_allowed_values()

        # If using a dictionary, extract values
        if channel_config:
            channel = channel_config.get("channel")
            gain = channel_config.get("gain")
            input = channel_config.get("input")
            shunt = channel_config.get("shunt")
            couple = channel_config.get("couple")
            filter = channel_config.get("filter")


        # Validate that channel is always provided
        if channel is None:
            raise ValueError("You must specify a channel to set or update!")

        # Fetch current settings if partial update
        current_config = self.getChannel(channel)  # Get existing values from the instrument
        if current_config is None:
            raise RuntimeError(f"Failed to retrieve current configuration for channel {channel}.")

        # Merge new values with existing ones
        updated_config = {
            "channel": channel,
            "gain": gain if gain is not None else current_config["gain"],
            "input": input if input is not None else current_config["input"],
            "shunt": shunt if shunt is not None else current_config["shunt"],
            "couple": couple if couple is not None else current_config["couple"],
            "filter": filter if filter is not None else current_config["filter"]
        }

        # Validate values
        if updated_config["channel"] not in allowed_values["channel"]:
            raise ValueError(f"Invalid channel: {updated_config['channel']}. Allowed values: {allowed_values['channel']}")
        if updated_config["gain"] not in allowed_values["gain"]:
            raise ValueError(f"Invalid gain: {updated_config['gain']}. Allowed values: {allowed_values['gain']}")
        if updated_config["input"] not in allowed_values["input"]:
            raise ValueError(f"Invalid input: {updated_config['input']}. Allowed values: {allowed_values['input']}")
        if updated_config["shunt"] not in allowed_values["shunt"]:
            raise ValueError(f"Invalid shunt: {updated_config['shunt']}. Allowed values: {allowed_values['shunt']}")
        if updated_config["couple"] not in allowed_values["couple"]:
            raise ValueError(f"Invalid couple: {updated_config['couple']}. Allowed values: {allowed_values['couple']}")
        if updated_config["filter"] not in allowed_values["filter"]:
            raise ValueError(f"Invalid filter: {updated_config['filter']}. Allowed values: {allowed_values['filter']}")

        # Send command
        cmd = 'setChannel'
        response = self._send_command(cmd, {"params": updated_config})
    
        if "error" in response:
            raise RuntimeError(f"Failed to set channel {channel}: {response['error']}")

        return response.get("result")


    def getChannel(self, channel):
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
        >>> print(kh.getChannel(channel = 1))
        {"channel": 1, "gain": 10, "input": "SE+", "shunt": 500, "couple": "AC", "filter": "ON"}
        """
        cmd = 'getChannel'
        params = {'channel': channel}
        response = self._send_command(cmd, params)
        result = response.get("result", {})

        # Helper function to parse integer values inside getChannel
        def parse_int(value, allowed=None):
            """
            Parses a value into an integer, stripping unwanted characters.
            Supports 'M' notation for megaohms (e.g., '10M' → 10000000) and 'k' for kiloohms(e.g., '5k' → 5000).

            Returns:
                int: The correctly parsed integer.

            Raises:
                ValueError: If the parsed value is not in the allowed list.
            """
            if isinstance(value, str):
                value = value.upper().replace("M", "000000")  # Convert '10M' to '10000000'
                value = ''.join(filter(str.isdigit, value))  # Remove non-numeric characters
            
            try:
                value = int(value)
                if allowed and value not in allowed:
                    raise ValueError(f"Invalid value: {value}. Allowed values: {allowed}")
                return value
            except ValueError:
                raise ValueError(f"Cannot convert '{value}' to a valid integer!")

        # Ensure numerical values are correctly formatted
        if "gain" in result:
            result["gain"] = parse_int(result["gain"], allowed=[1, 10, 100, 1000])  # Ensure it's a valid integer
        if "shunt" in result:
            result["shunt"] = parse_int(result["shunt"], allowed=[0, 50, 500, 5000, 50000, 10000000])  # Ensure it's valid

        return response.get('result')

    
if __name__ == "__main__":
    # Test the KH7008 class
    kh = KH7008("tcp://localhost:29160",)
    
    # channel_config = {
    #    "channel": 1,
    #    "gain": 10,
    #    "input": 'SE+',
    #    "shunt": 50,
    #    "couple": "AC",
    #    "filter": "ON",
    # }
    # kh.setChannel(channel_config)

    #kh.setChannel(channel=1, couple="DC", input= "SE-", gain= 100)
    # time.sleep(0.5)
    print(kh.getChannel(channel = 1))
    kh.close()