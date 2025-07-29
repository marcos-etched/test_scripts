Quick start  
1. Check PSU status  
   python psu_ctrl.py status

2. Configure PSU voltage=54V and current (limit)=5A  
   	sudo python psu_ctrl.py configure -v 54 -i 5

3. Power off  
   	sudo python psu_ctrl.py power_off
4. Power on  
   	sudo python psu_ctrl.py power_on  
5. Capture PSU Telemetry (VOUT, IOUT, POUT)  
	sudo python psu_ctrl.py telemetry

Help menus  
sohu@raspberrypi:~/scripts/psu $ python psu_ctrl.py -h  
usage: psu_ctrl.py [-h] [device] {configure,power_on,power_off,status,telemetry} ...  
  
PSU Control Script
  
positional arguments:  
  device                PSU device path (default: /dev/usbtmc0)  
  {configure,power_on,power_off,status,telemetry}  
                        Available commands  
    configure           Configure PSU parameters  
    power_on            Turn on PSU  
    power_off           Turn off PSU  
    status              Get PSU status  
    telemetry           Monitor PSU telemetry  
  
options:  
  -h, --help            show this help message and exit  
  
sohu@raspberrypi:~/scripts/psu $ python psu_ctrl.py configure -h  
usage: psu_ctrl.py [device] configure [-h] -v VOLTAGE -i CURRENT  
  
options:  
  -h, --help            show this help message and exit  
  -v VOLTAGE, --voltage VOLTAGE  
                        Set output voltage  
  -i CURRENT, --current CURRENT  
                        Set current limit  
