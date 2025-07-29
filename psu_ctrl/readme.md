Quick start  
1. Check PSU status  
   python psu_ctrl.py status

2. Configure PSU voltage=54V and current (limit)=5A  
   	python psu_ctrl.py configure -v 54 -i 5

3. Power off  
   	python psu_ctrl.py power_off
4. Power on  
   	python psu_ctrl.py power_on  
5. Capture PSU Telemetry (VOUT, IOUT, POUT)  
	python psu_ctrl.py telemetry

See Help menu with -h argument for more information
