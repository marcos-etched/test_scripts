#!/bin/bash

########################################################################
#
# Wrapper script to capture PCIe details of the Vertical BaseBoard (VBB)
#
########################################################################

log_config_space_regs() {
	local bdf="$1"
	printf "# sudo lspci -vvvs $bdf\n" >> $lnksta_log
	sudo lspci -vvvs $bdf >> $lnksta_log	
#	printf "# sudo lspci -xxxxs $bdf\n" >> $lnksta_log
#	sudo lspci -xxxxs $bdf >> $lnksta_log	

}

get_link_status() {
	local bdf="$1"
	local dev="/sys/bus/pci/devices/$bdf"
	local speed width
	if [[ -r "$dev/current_link_speed" && -r "$dev/current_link_width" ]]; then
		read -r speed < "$dev/current_link_speed"
		read -r width < "$dev/current_link_width"
	else
		local lnk
		lnk="$(sudo lspci -vvvs "$bdf" | awk '/LnkSta:/{print; exit}')"
		speed="$(sed -n 's/.*Speed \([0-9.]\+GT\/s\).*/\1/p' <<<"$lnk")"
		width="$(sed -n 's/.*Width x\([0-9]\+\).*/\1/p' <<<"$lnk")"
	fi
	case "$speed" in
		"2.5 GT/s PCIe")
			gen_speed=1;;
		"5.0 GT/s PCIe")
			gen_speed=2;;
		"8.0 GT/s PCIe")
			gen_speed=3;;
		"16.0 GT/s PCIe")
			gen_speed=4;;
		"32.0 GT/s PCIe")
			gen_speed=5;;
		"64.0 GT/s PCIe")
			gen_speed=6;;
		"Unknown")
			gen_speed="Unknown";;
	esac

	printf 'Gen%sx%s' "$gen_speed" "$width"
}


get_aer_counts() {
	local bdf="$1"
	local dev="/sys/bus/pci/devices/$bdf"
	local ue=0 ce=0 fatal=0 nonfatal=0 correctable=0

	if [[ -r "$dev/aer_dev_fatal" && -r "$dev/aer_dev_nonfatal" && -r "$dev/aer_dev_correctable" ]]; then
		# Extract TOTAL_* if present; else sum every numeric field (positions 2,4,6,...)
		fatal=$(sed -n 's/.*TOTAL_ERR_FATAL \([0-9]\+\).*/\1/p' "$dev/aer_dev_fatal")
		[[ -z $fatal ]] && fatal=$(awk '{s=0; for(i=2;i<=NF;i+=2) s+=$i; print s}' "$dev/aer_dev_fatal")

		nonfatal=$(sed -n 's/.*TOTAL_ERR_NONFATAL \([0-9]\+\).*/\1/p' "$dev/aer_dev_nonfatal")
		[[ -z $nonfatal ]] && nonfatal=$(awk '{s=0; for(i=2;i<=NF;i+=2) s+=$i; print s}' "$dev/aer_dev_nonfatal")

		correctable=$(sed -n 's/.*TOTAL_ERR_CORRECTABLE \([0-9]\+\).*/\1/p' "$dev/aer_dev_correctable")
		[[ -z $correctable ]] && correctable=$(awk '{s=0; for(i=2;i<=NF;i+=2) s+=$i; print s}' "$dev/aer_dev_correctable")

		ue=$(( fatal + nonfatal ))
		ce=$(( correctable ))
	else
		# Fallback: lspci UESta/CESta “+” counts
		read -r ue ce < <(
		sudo lspci -s "$bdf" -vvv 2>/dev/null | awk '
			/UESta:/ {c=0; for(i=2;i<=NF;i++) if ($i ~ /\+$/) c++; ue=c}
			/CESta:/ {c=0; for(i=2;i<=NF;i++) if ($i ~ /\+$/) c++; ce=c}
			END {printf "%d %d\n", (ue?ue:0), (ce?ce:0)}
			'
		)
		ue=${ue:-0}; ce=${ce:-0}
	fi

	printf '%d %d\n' "$ue" "$ce"
}


# Sum AER across a group of BDFs (endpoint .0, endpoint .1, downstream port)
# Prints "UE CE" total for the group.
sum_aer_group() {
	local ue_total=0 ce_total=0 ue ce bdf
	for bdf in "$@"; do
		# Skip empty/missing entries safely
		[[ -n "$bdf" && -e "/sys/bus/pci/devices/$bdf" ]] || continue
		read -r ue ce < <(get_aer_counts "$bdf")
		ue_total=$(( ue_total + ue ))
		ce_total=$(( ce_total + ce ))
	done
	printf '%d %d\n' "$ue_total" "$ce_total"
}

get_kernel_log_bdf() {
	local bdf="$1"
	printf "# sudo dmesg | grep $bdf\n" >> $dmesg_log
	printf '%s\n\n' "$dmesg" | grep $bdf >> $dmesg_log
}

########### main ##########
mapfile -t ep_bdfs_0 < <(lspci | grep NVIDIA | cut -d ' ' -f1 | grep -o '[0-9a-f]\{4\}:[0-9a-f]\{2\}:[0-9a-f]\{2\}\.0')
mapfile -t ep_bdfs_1 < <(lspci | grep NVIDIA | cut -d ' ' -f1 | grep -o '[0-9a-f]\{4\}:[0-9a-f]\{2\}:[0-9a-f]\{2\}\.1')

gpu_cnt=${#ep_bdfs_0[@]}
if [[ $gpu_cnt -eq 0 ]]; then
	printf 'No endpoints detected. Exiting...\n'
	exit 1
fi

date=`date +"%m%d%y"`
if [[ $gpu_cnt -eq 1 ]]; then
	lnksta_log="logs/${date}_vbb_pcie_gen5_gpu_lnksta.log"
	dmesg_log="logs/${date}_vbb_pcie_gen5_gpu_dmesg.log"
else
	lnksta_log="logs/${date}_vbb_pcie_gen5_${gpu_cnt}gpus_lnksta.log"
	dmesg_log="logs/${date}_vbb_pcie_gen5_${gpu_cnt}gpus_dmesg.log"

fi
declare -A dsp_bdfs
declare -A lnk_sta
declare -A aer_summary

cnt=0
for bdf in "${ep_bdfs_0[@]}"; do
	sys="/sys/bus/pci/devices/$bdf"
	[[ -e "$sys" ]] || continue
	dsp_bdf=$(basename "$(dirname "$(readlink -f "$sys")")")
	dsp_bdfs[$cnt]=$dsp_bdf
	((cnt++))
done

# Capture PCIe topology
printf  "# lspci\n" > $lnksta_log
lspci >> $lnksta_log
#printf "# lspci -tv\n" >> $lnksta_log
#lspci -tv >> $lnksta_log
printf "\n# /home/sohu/venvs/pcicrawler/bin/pcicrawler -tv\n" >> $lnksta_log
/home/sohu/venvs/pcicrawler/bin/pcicrawler -tv 2>&1 | grep -v "^It looks like" >> $lnksta_log
echo "" >> $lnksta_log

# Capture full kernel log
printf  "# dmesg\n" > $dmesg_log
dmesg="$(sudo dmesg)"
printf '%s\n\n' "$dmesg" >> $dmesg_log

# Capture Config space, link status, AERs, and kernel log
for i in "${!ep_bdfs_0[@]}"; do
	case "${ep_bdfs_0[$i]}" in
		"0000:18:00.0")
			printf '##### Retimer7 - PCIE7 #####\n' | tee -a "$lnksta_log" "$dmesg_log" > /dev/null;;
		"0000:6d:00.0")
			printf '##### Retimer6 - PCIE4 #####\n' | tee -a "$lnksta_log" "$dmesg_log" > /dev/null;;
		"0000:c0:00.0")
			printf '##### Retimer5 - PCIE3 #####\n' | tee -a "$lnksta_log" "$dmesg_log" > /dev/null;;
		"0000:97:00.0")
			printf '##### Retimer4 - PCIE0 #####\n' | tee -a "$lnksta_log" "$dmesg_log" > /dev/null;;
		"0001:19:00.0")
			printf '##### Retimer3 - PCIE1 #####\n' | tee -a "$lnksta_log" "$dmesg_log" > /dev/null;;
		"0001:6c:00.0")
			printf '##### Retimer2 - PCIE2 #####\n' | tee -a "$lnksta_log" "$dmesg_log" > /dev/null;;
		"0001:96:00.0")
			printf '##### Retimer1 - PCIE5 #####\n' | tee -a "$lnksta_log" "$dmesg_log" > /dev/null;;
		"0001:c1:00.0")
			printf '##### Retimer0 - PCIE6 #####\n' | tee -a "$lnksta_log" "$dmesg_log" > /dev/null;;
	esac

	#Config Space Capture
	log_config_space_regs "${dsp_bdfs[$i]}"
	log_config_space_regs "${ep_bdfs_0[$i]}"
	log_config_space_regs "${ep_bdfs_1[$i]}"

	#Link Status Capture
	lnk_sta[$i]="$(get_link_status "${ep_bdfs_0[$i]}")"

	#AER Capture
	read -r ue ce < <(sum_aer_group "${dsp_bdfs[$i]} ${ep_bdfs_0[$i]} ${ep_bdfs_1[$i]}")
	aer_summary["$i"]="UE=$ue CE=$ce"

	#Kernel log capture
	get_kernel_log_bdf ${dsp_bdfs[$i]}
	get_kernel_log_bdf ${ep_bdfs_0[$i]}
	get_kernel_log_bdf ${ep_bdfs_1[$i]}
	echo "" >> $dmesg_log

#	printf "# sudo dmesg | grep ${dsp_bdfs[$i]}\n" >> $dmesg_log
#	echo "$dmesg" | grep ${dsp_bdfs[$i]} >> $dmesg_log
#	printf "# sudo dmesg | grep ${ep_bdfs_0[$i]}\n" >> $dmesg_log
#	echo "$dmesg" | grep ${ep_bdfs_0[$i]} >> $dmesg_log
#	printf "# sudo dmesg | grep ${ep_bdfs_1[$i]}\n" >> $dmesg_log
#	echo "$dmesg" | grep ${ep_bdfs_1[$i]} >> $dmesg_log
	
done

printf '\n===== PCIe Link Status =====\n' >> $lnksta_log
for i in "${!ep_bdfs_0[@]}"; do
	printf '%-s: %s\n' "${ep_bdfs_0[$i]}" "${lnk_sta[$i]}" >> $lnksta_log
done

printf '\n===== PCIe AER Summary =====\n' >> $lnksta_log
for i in "${!ep_bdfs_0[@]}"; do
	printf '%-s -> %s, %s\n   AER: %s\n' "${dsp_bdfs[$i]}" "${ep_bdfs_0[$i]}" "${ep_bdfs_1[$i]}" "${aer_summary[$i]}" >> $lnksta_log
done

cat $lnksta_log
