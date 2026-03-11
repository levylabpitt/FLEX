# %% - Test CESession
from flex.exp.CESession import CESession
exp = CESession()


# %% - Testing Context Manager approach
with CESession(timeout=5.0, verbose=True) as myexp:
    # Everything inside this block is "safe"
    print(myexp.DAQ.help())
# Instruments are closed automatically here!
# %%
