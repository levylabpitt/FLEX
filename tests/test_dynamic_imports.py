import importlib
import pkgutil

def dynamic_import_and_instantiate_by_name(instrument_name):
    package = importlib.import_module('flex.inst.levylab')
    
    # Iterate over all modules in the package
    for _, module_name, _ in pkgutil.iter_modules(package.__path__):
        try:
            # Import the module dynamically
            module = importlib.import_module(f"flex.inst.levylab.{module_name}")

            # Check if _LABVIEW_CLASS_NAME matches
            if hasattr(module, '_LABVIEW_CLASS_NAME') and module._LABVIEW_CLASS_NAME == instrument_name:
                # Get the class with the same name as the module and instantiate it
                instrument_class = getattr(module, module_name)
                return instrument_class()  # Instantiate the class

        except Exception as e:
            continue

    return None

# Example usage:
instrument_names = ["Instrument.Lockin.lvclass", "instrument.PPMS.lvclass"]

for name in instrument_names:
    instrument = dynamic_import_and_instantiate_by_name(name)
    if instrument:
        print(f"Successfully instantiated {instrument}")
    else:
        print(f"Failed to instantiate for {name}")