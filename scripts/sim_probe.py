from isaacsim import SimulationApp
app=SimulationApp({'headless':True,'width':640,'height':480})
from pxr import Usd
print('SIM_STARTED',Usd.GetVersion(),flush=True)
app.close()
