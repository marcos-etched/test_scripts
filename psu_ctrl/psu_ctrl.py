#!/usr/bin/env python3
import time
import argparse
import sys
import os
import csv
import datetime
import signal

CRLF = b"\r\n"
buffer_delay = 0.1  # seconds, to allow the PSU to process commands
on_delay = 0.5  # seconds, to allow the PSU to turn on

# Global variables
running = True
DEV = None

def signal_handler(sig, frame):
    global running
    print("\n")
    print("Stopping data acquisition...")
    running = False

def send_command(command):
    """Send a command to the PSU"""
    with open(DEV, "wb", buffering=0) as w:
        w.write(command + CRLF)
    time.sleep(buffer_delay)

def read_response():
    """Read response from the PSU"""
    with open(DEV, "rb", buffering=0) as r:
        return r.read(1024).decode(errors="replace").strip()

def query_psu(command):
    """Send a query command and return the response"""
    send_command(command)
    return read_response()

def check_psu_connection():
    """Check if PSU is connected and responding"""
    try:
        idn = query_psu(b"*IDN?")
        if idn.startswith("*IDN?") or not idn or len(idn.split(',')) < 2:
            return False, "Invalid IDN response"
        return True, idn
    except Exception as e:
        return False, str(e)

def get_psu_settings():
    """Get current voltage and current settings from PSU"""
    try:
        voltage = float(query_psu(b"VOLT?"))
        current = float(query_psu(b"CURR?"))
        return voltage, current
    except Exception as e:
        raise Exception(f"Failed to read PSU settings: {e}")

def configure_psu(voltage, current):
    """Configure PSU parameters"""
    print(f"Configuring PSU: {voltage}V, {current}A limit")
    
    try:
        # Turn remote ON
        send_command(b"SYST:REM")

        # Set voltage
        send_command(f"VOLT {voltage}".encode())
        
        # Set current limit
        send_command(f"CURR {current}".encode())
        
        # Verify settings
        voltage_set = query_psu(b"VOLT?")
        current_set = query_psu(b"CURR?")
        
        print(f"✅ PSU configured successfully")
        print(f"Verified settings: {float(voltage_set):.2f}V, {float(current_set):.2f}A")
        
        # Turn remote OFF (return to local control)
        send_command(b"SYST:LOC")

        return True
        
    except Exception as e:
        print(f"❌ ERROR during configuration: {e}")
        return False

def capture_telemetry(sampling_rate=1.0, psu_idn=None):
    """Telemetry capture function"""
    # Set up signal handler for Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)

    # Get the actual settings being used
    actual_voltage, actual_current = get_psu_settings()
    
    # Parse IDN string to extract components
    idn_parts = psu_idn.split(',') if psu_idn else ['Unknown', 'Unknown', 'Unknown', 'Unknown']
    manufacturer = idn_parts[0] if len(idn_parts) > 0 else 'Unknown'
    model = idn_parts[1] if len(idn_parts) > 1 else 'Unknown'
    serial = idn_parts[2] if len(idn_parts) > 2 else 'Unknown'
    firmware = idn_parts[3] if len(idn_parts) > 3 else 'Unknown'
    
    csv_writer = None
    csvfile = None
    
    # Create logs directory if it doesn't exist
    logs_dir = "/home/sohu/scripts/psu/logs"
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir)
        print(f"Created logs directory: {logs_dir}")
    
    # Create CSV filename with timestamp in logs directory
    timestamp = datetime.datetime.now().strftime("%Y_%m_%d_%H%M%S")
    filename = os.path.join(logs_dir, f"telem_psu_sn{serial}_{timestamp}.csv")
    
    print(f"Saving data to: {filename}")
    
    # Create CSV file and write header
    csvfile = open(filename, 'w', newline='')
    csv_writer = csv.writer(csvfile)
    
    # Write header using actual IDN information
    csv_writer.writerow(['Instrument ID:', manufacturer, model, serial, firmware, ''])
    csv_writer.writerow(['', '', '', '', '', ''])
    csv_writer.writerow(['', '', '', '', 'Sampling Rate:', f"{sampling_rate}s"])
    start_time = datetime.datetime.now()
    csv_writer.writerow(['', '', '', '', 'Start Time:', start_time.strftime('%m/%d/%Y %I:%M:%S %p')])
    csv_writer.writerow(['', '', '', '', '', ''])
    csv_writer.writerow(['Time', 'Voltage', 'Current', 'Power', '', ''])
    
    print(f"Starting telemetry monitoring at {actual_voltage}V, {actual_current}A. Press Ctrl+C to stop.")
    print()  # Add blank line before table
    print("VOUT (V)  | IOUT (A)  | POUT (W)")
    print("-" * 30)
    
    # Data acquisition loop
    measurement_count = 0
    
    # Wait for the next whole second to start measurements at 0ms
    current_time = time.time()
    next_whole_second = int(current_time) + 1
    sleep_until_start = next_whole_second - current_time
    
    time.sleep(sleep_until_start)
    
    # Now schedule measurements starting from this synchronized time
    next_measurement_time = next_whole_second + sampling_rate
    
    try:
        while running:
            try:
                # Capture timestamp at the start of measurement cycle for more accurate timing
                measurement_start_time = datetime.datetime.now()
                time_str = measurement_start_time.strftime('%H:%M:%S.%f')[:-3]  # Remove last 3 digits to get milliseconds
                
                # Get measurements
                voltage_meas = query_psu(b"MEAS:VOLT?")
                current_meas = query_psu(b"MEAS:CURR?")
                power_meas = query_psu(b"MEAS:POW?")
                
                # Write data row to CSV
                csv_writer.writerow([time_str, f"{float(voltage_meas):.6f}", f"{float(current_meas):.6f}", f"{float(power_meas):.6f}"])
                
                measurement_count += 1
                # Display telemetry readings in table format (overwrite previous line)
                print(f"\r{float(voltage_meas):8.3f}  | {float(current_meas):8.3f}  | {float(power_meas):8.3f}", end='', flush=True)
                
                # Calculate precise sleep time to maintain consistent intervals
                current_time_sec = time.time()
                sleep_time = next_measurement_time - current_time_sec
                
                if sleep_time > 0:
                    time.sleep(sleep_time)
                else:
                    # If we're running behind, skip ahead to stay on schedule
                    print(f"Warning: Running {-sleep_time:.3f}s behind schedule")
                
                # Schedule next measurement
                next_measurement_time += sampling_rate
                
            except Exception as e:
                print(f"Error during measurement: {e}")
                break
    
    finally:
        # Close CSV file
        if csvfile:
            csvfile.close()
        
        print(f"\nTelemetry monitoring stopped. {measurement_count} measurements collected.")
        print(f"Data saved to {filename}")
        
        send_command(b"SYST:BEEP ON")

def power_on():
    """Turn on PSU"""
    try:
        # Get the actual settings being used
        actual_voltage, actual_current = get_psu_settings()
        print(f"Powering on PSU: {actual_voltage}V, {actual_current}A limit")

        # Turn remote ON
        send_command(b"SYST:REM")

        # Turn output ON
        send_command(b"OUTP ON")
        time.sleep(on_delay)

        # Check if output failed to turn on
        output_status = query_psu(b"OUTP?")
        if output_status.strip() == "0":
            print(f"❌ Failed to power on.")
            return False

        print("✅ PSU powered on successfully")

        # Get current measurements
        voltage_meas = query_psu(b"MEAS:VOLT?")
        current_meas = query_psu(b"MEAS:CURR?")
        power_meas = query_psu(b"MEAS:POW?")

        print(f"Measurements: {float(voltage_meas):.3f}V, {float(current_meas):.3f}A, {float(power_meas):.3f}W")

        # Turn remote OFF (return to local control)
        send_command(b"SYST:LOC")

        return True

    except Exception as e:
        print(f"❌ ERROR during power on: {e}")
        return False

def power_off():
    """Turn off PSU"""
    print("Powering off PSU...")
    
    try:
        # Turn remote ON
        send_command(b"SYST:REM")

        # Turn output OFF
        send_command(b"OUTP OFF")

        # Check if output failed to turn off
        output_status = query_psu(b"OUTP?")
        if output_status.strip() == "1":
            print(f"❌ Failed to power off.")
            return False

        print("✅ PSU powered off successfully")
        
        # Turn remote OFF (return to local control)
        send_command(b"SYST:LOC")
        
        return True
        
    except Exception as e:
        print(f"❌ ERROR during power off: {e}")
        return False

def get_status():
    """Get current PSU status"""
    print("Checking PSU status...")
    
    try:
        # Get output status
        output_status = query_psu(b"OUTP?")
        is_on = output_status.strip() == "1"
        
        if is_on:
            print("Output: ON")
        else:
            print("Output: OFF")

        # Get current measurements
        voltage_set = query_psu(b"VOLT?")
        current_set = query_psu(b"CURR?")
        voltage_meas = query_psu(b"MEAS:VOLT?")
        current_meas = query_psu(b"MEAS:CURR?")
        power_meas = query_psu(b"MEAS:POW?")
        
        print(f"Settings: {float(voltage_set):.2f}V, {float(current_set):.2f}A")
        print(f"Measurements: {float(voltage_meas):.3f}V, {float(current_meas):.3f}A, {float(power_meas):.3f}W")
        
        return True
        
    except Exception as e:
        print(f"❌ ERROR getting status: {e}")
        return False

def main():
    """Main function to handle command line arguments"""
    global DEV
    
    parser = argparse.ArgumentParser(description='PSU Control Script')
    
    # Add device as first positional argument with default
    parser.add_argument('device', nargs='?', default='/dev/usbtmc0',
                       help='PSU device path (default: /dev/usbtmc0)')
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Configure command
    configure_parser = subparsers.add_parser('configure', help='Configure PSU parameters')
    configure_parser.add_argument('-v', '--voltage', type=float, required=True,
                                 help='Set output voltage')
    configure_parser.add_argument('-i', '--current', type=float, required=True,
                                 help='Set current limit')
    
    # Power on command
    subparsers.add_parser('power_on', help='Turn on PSU')
    
    # Power off command
    subparsers.add_parser('power_off', help='Turn off PSU')
    
    # Status command
    subparsers.add_parser('status', help='Get PSU status')
    
    # Telemetry command
    telemetry_parser = subparsers.add_parser('telemetry', help='Monitor PSU telemetry')
    telemetry_parser.add_argument('-r', '--rate', type=float, default=1.0,
                                 help='Sampling rate in seconds (default: 1.0s)')
    
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        return

    # Set the global device variable
    DEV = args.device

    # Check if device exists
    if not os.path.exists(DEV):
        print(f"❌ ERROR: Device {DEV} not found")
        print("Please check if the PSU is connected and the device is accessible")
        sys.exit(1)

    # Turn off beeping
    send_command(b"SYST:BEEP OFF")

    # Set communication to USB
    send_command(b"SYST:INT USB")

    # Check PSU connection
    connected, result = check_psu_connection()
    if not connected:
        print(f"❌ ERROR: PSU communication failed - {result}")
        print("Please check:")
        print("- PSU is powered on")
        print("- Root privileges")
        print("- USB cable is connected properly")
        print("- No other software is using the PSU")
        print(f"- Device {DEV} exists and is accessible")
        return False
    
    print(f"✅ PSU detected: {result}")

    # Execute command
    if args.command == 'configure':
        success = configure_psu(args.voltage, args.current)
        sys.exit(0 if success else 1)
    elif args.command == 'power_on':
        success = power_on()
        sys.exit(0 if success else 1)
    elif args.command == 'power_off':
        success = power_off()
        sys.exit(0 if success else 1)
    elif args.command == 'status':
        success = get_status()
        sys.exit(0 if success else 1)
    elif args.command == 'telemetry':
        success = capture_telemetry(args.rate, result)
        sys.exit(0 if success else 1)

    # Turn beeping back on
    send_command(b"SYST:BEEP ON")

if __name__ == "__main__":
    main()