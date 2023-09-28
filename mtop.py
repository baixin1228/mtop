#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# @Time    : 2023/9/16
# @Author  : baixin
# @File    : mtop.py
# @Lisence : GPL-2.0

import os
import re
import sys
import tty
import time
import select
import signal
import termios
import platform
import resource
import datetime
import argparse

exit = False
cpu_detal = True
disk_detal = False
time_interval = 1

def getchar(timeout = 1):
	c = ''
	fd = sys.stdin.fileno()
	old_settings = termios.tcgetattr(fd)
	new_term = termios.tcgetattr(fd)
	try:
		# new_term[3] = (new_term[3] & ~termios.ICANON & ~termios.ECHO)
		new_term[3] = (new_term[3] & ~(termios.ICANON | termios.ECHO))
		termios.tcsetattr(fd, termios.TCSANOW, new_term)
		if select.select([sys.stdin], [], [], timeout)[0]:
			c = sys.stdin.read(1)
	finally:
		termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
		sys.stdout.flush()
	return c

def check_input(timeout):
	global cpu_detal, disk_detal
	userInput = getchar(timeout).lower()
	if userInput == "q":
		sys.exit(0)
	elif userInput == "c":
		cpu_detal = not cpu_detal
	elif userInput == "d":
		disk_detal = not disk_detal

def format_number(number):
	if number < 1000:
		return str(number)

	if number < 1000000:
		return "%.1fk" % (number / 1000)

	if number < 1000000000:
		return "%.1fM" % (number / 1000000)

	if number < 1000000000000:
		return "%.1fG" % (number / 1000000000)

	if number < 1000000000000000:
		return "%.1fT" % (number / 1000000000000)

def format_color(number, div):
	if number > div:
		return {"ctrl_count" : 11, "str" : f"\033[1;31m{number}%\033[0m"}
	else:
		return {"ctrl_count" : 0, "str" : "%s%%" % str(number)}

def run():
	cpu_re = re.compile(r"(cpu[0-9]*) *([0-9]+) ([0-9]+) ([0-9]+) ([0-9]+) ([0-9]+) ([0-9]+) ([0-9]+) ([0-9]+) ([0-9]+) ([0-9]+)")
	meminfo_re = re.compile(r"MemTotal.*?([0-9]+).*kB.*MemFree.*?([0-9]+).*kB.*MemAvailable.*?([0-9]+).*kB.*Buffers.*?([0-9]+).*?kB.*?Cached.*?([0-9]+)", re.S)
	diskinfo_re = re.compile(r"^ *(8|259) *[0-9]+ (sd[a-zA-Z]+[0-9]*|nvme[0-9]+n[0-9]+p*[0-9]*) ([0-9]+) ([0-9]+) ([0-9]+) ([0-9]+) ([0-9]+) ([0-9]+) ([0-9]+) ([0-9]+) ([0-9]+) ([0-9]+) ([0-9]+)", re.M)
	disk_filter= re.compile(r"^sd[a-zA-Z]+$|nvme[0-9]+n[0-9]+$")
	process_dir_re = re.compile(r"^/proc/[0-9]+", re.M)
	processinfo_re = re.compile(r"^([0-9]+) \((.+)\) ([A-Z]+) ([\-0-9]+) ([\-0-9]+) ([\-0-9]+) ([\-0-9]+) ([\-0-9]+) ([\-0-9]+) ([\-0-9]+) ([\-0-9]+) ([\-0-9]+) ([\-0-9]+) ([\-0-9]+) ([\-0-9]+) ([\-0-9]+) ([\-0-9]+) ([\-0-9]+) ([\-0-9]+) ([\-0-9]+) ([\-0-9]+) ([\-0-9]+) ([\-0-9]+) ([\-0-9]+) ([\-0-9]+) ([\-0-9]+) ([\-0-9]+) ([\-0-9]+) ([\-0-9]+) ([\-0-9]+) ([\-0-9]+) ([\-0-9]+) ([\-0-9]+) ([\-0-9]+) ([\-0-9]+) ([\-0-9]+) ([\-0-9]+) ([\-0-9]+) ([\-0-9]+) ([\-0-9]+) ([\-0-9]+) ([\-0-9]+) ([\-0-9]+) ([\-0-9]+) ([\-0-9]+) ([\-0-9]+) ", re.M)
	processstatus_re = re.compile(r"Uid.*?([0-9]+)")
	users_re = re.compile(r"^(.*?):(.*?):(.*?):", re.M)
	userid_to_name = {}
	if os.path.exists("/etc/passwd"):
		with open("/etc/passwd") as f:
			users_str = f.read()
			usersid_iter = users_re.finditer(users_str)
			for userid in usersid_iter:
				userid_to_name[userid.group(3)] = userid.group(1)

	last_time_ms = {"proc" : 0, "diskstats" : 0, "proc" : 0, "proc" : 0}
	cpu_infos_sub = {}
	cpu_infos_last = {}
	disk_infos_sub = {}
	disk_infos_last = {}
	process_infos_sub = {}
	process_infos_last = {}
	max_item_col = 0
	mode = "all"
	print("\033[2J")
	while not exit:
		total_mem = 0
		print_lines = []
		if os.path.exists("/proc/stat"):
			with open("/proc/stat", "r") as f:
				f.seek(0)
				stat_str = f.read()
				time_sub = time.time() * 1000 - last_time_ms["proc"]
				cpu_info_iter = cpu_re.finditer(stat_str)
				
				for i in cpu_info_iter:
					cpu_info = {}
					cpu_info["user"] = int(i.group(2))
					cpu_info["nice"] = int(i.group(3))
					cpu_info["system"] = int(i.group(4))
					cpu_info["idle"] = int(i.group(5))
					cpu_info["iowait"] = int(i.group(6))
					cpu_info["irq"] = int(i.group(7))
					cpu_info["softirq"] = int(i.group(8))
					cpu_info["steal"] = int(i.group(9))
					cpu_info["guest"] = int(i.group(10))
					cpu_info["guest_nice"] = int(i.group(11))

					key = i.group(1)
					if key not in cpu_infos_last:
						cpu_infos_last[key] = cpu_info
					else:
						cpu_info_sub = {}
						cpu_info_sub["user"] = cpu_info["user"] - cpu_infos_last[key]["user"]
						cpu_info_sub["nice"] = cpu_info["nice"] - cpu_infos_last[key]["nice"]
						cpu_info_sub["system"] = cpu_info["system"] - cpu_infos_last[key]["system"]
						cpu_info_sub["idle"] = cpu_info["idle"] - cpu_infos_last[key]["idle"]
						cpu_info_sub["iowait"] = cpu_info["iowait"] - cpu_infos_last[key]["iowait"]
						cpu_info_sub["irq"] = cpu_info["irq"] - cpu_infos_last[key]["irq"]
						cpu_info_sub["softirq"] = cpu_info["softirq"] - cpu_infos_last[key]["softirq"]
						cpu_info_sub["steal"] = cpu_info["steal"] - cpu_infos_last[key]["steal"]
						cpu_info_sub["guest"] = cpu_info["guest"] - cpu_infos_last[key]["guest"]
						cpu_info_sub["guest_nice"] = cpu_info["guest_nice"] - cpu_infos_last[key]["guest_nice"]
						if key in cpu_infos_sub:
							del(cpu_infos_sub[key])

						del(cpu_infos_last[key])
						cpu_infos_last[key] = cpu_info
						cpu_infos_sub[key] = cpu_info_sub


				for key, value in cpu_infos_sub.items():
					cpu_usage_user = int(value["user"] * 1000 / time_sub )
					cpu_usage_sys = int(value["system"] * 1000 / time_sub )
					cpu_usage_nice = int(value["nice"] * 1000 / time_sub )
					cpu_usage_irq = int(value["irq"] * 1000 / time_sub )
					cpu_usage_soft = int(value["softirq"] * 1000 / time_sub )
					cpu_usage_idle = int(value["idle"] * 1000 / time_sub )
					cpu_usage_iowait = int(value["iowait"] * 1000 / time_sub )
					cpu_freq = 0
					if os.path.exists("/sys/devices/system/cpu/%s/cpufreq/scaling_cur_freq" % key):
						with open("/sys/devices/system/cpu/%s/cpufreq/scaling_cur_freq" % key, "r") as cpu_freq_f:
							cpu_freq = int(cpu_freq_f.read()) * 1000

					cpu_max = 0
					if os.path.exists("/sys/devices/system/cpu/%s/cpufreq/scaling_max_freq" % key):
						with open("/sys/devices/system/cpu/%s/cpufreq/scaling_max_freq" % key, "r") as cpu_max_f:
							cpu_max = int(cpu_max_f.read()) * 1000

					cpu_gov = "-"
					if os.path.exists("/sys/devices/system/cpu/%s/cpufreq/scaling_governor" % key):
						with open("/sys/devices/system/cpu/%s/cpufreq/scaling_governor" % key, "r") as cpu_gov_f:
							cpu_gov = cpu_gov_f.read()[:-1]

					line = []
					if key == "cpu":
						usage_max = 90 * len(cpu_infos_sub)
					else:
						usage_max = 90

					line.append([{"ctrl_count" : 0, "str" : key}, {"ctrl_count" : 0, "str" : ""}])
					line.append([{"ctrl_count" : 0, "str" : "user:"}, format_color(cpu_usage_user, usage_max)])
					line.append([{"ctrl_count" : 0, "str" : "sys:"}, format_color(cpu_usage_sys, usage_max)])
					line.append([{"ctrl_count" : 0, "str" : "nice:"}, format_color(cpu_usage_nice, usage_max)])
					line.append([{"ctrl_count" : 0, "str" : "irq:"}, format_color(cpu_usage_irq, usage_max)])
					line.append([{"ctrl_count" : 0, "str" : "soft:"}, format_color(cpu_usage_soft, usage_max)])
					line.append([{"ctrl_count" : 0, "str" : "idle:"}, {"ctrl_count" : 0, "str" : "%s%%" % str(cpu_usage_idle)}])
					line.append([{"ctrl_count" : 0, "str" : "iowait:"}, format_color(cpu_usage_iowait, usage_max)])
					line.append([{"ctrl_count" : 0, "str" : "freq:"}, {"ctrl_count" : 0, "str" : format_number(cpu_freq)}])
					line.append([{"ctrl_count" : 0, "str" : "max:"}, {"ctrl_count" : 0, "str" : format_number(cpu_max)}])
					line.append([{"ctrl_count" : 0, "str" : "gov:"}, {"ctrl_count" : 0, "str" : cpu_gov}])
					if len(line) > max_item_col:
						max_item_col = len(line)

					print_lines.append(line)
					if key == "cpu" and not cpu_detal:
						break

			last_time_ms["proc"] = time.time() * 1000

		if os.path.exists("/proc/meminfo"):
			with open("/proc/meminfo", "r") as f:
				meminfo_str = f.read()
				meminfo = meminfo_re.match(meminfo_str)
				total_mem = int(meminfo.group(1)) * 1000
				free_mem = int(meminfo.group(2)) * 1000
				avail_mem = int(meminfo.group(3)) * 1000
				buf_mem = int(meminfo.group(4)) * 1000
				cache_mem = int(meminfo.group(5)) * 1000

				line = []
				line.append([{"ctrl_count" : 0, "str" : "mem"}, {"ctrl_count" : 0, "str" : ""}])
				line.append([{"ctrl_count" : 0, "str" : "total:"}, {"ctrl_count" : 0, "str" : format_number(total_mem)}])
				line.append([{"ctrl_count" : 0, "str" : "free:"}, {"ctrl_count" : 0, "str" : format_number(free_mem)}])
				line.append([{"ctrl_count" : 0, "str" : "avail:"}, {"ctrl_count" : 0, "str" : format_number(avail_mem)}])
				line.append([{"ctrl_count" : 0, "str" : "bufs:"}, {"ctrl_count" : 0, "str" : format_number(buf_mem)}])
				line.append([{"ctrl_count" : 0, "str" : "cached:"}, {"ctrl_count" : 0, "str" : format_number(cache_mem)}])
				if len(line) > max_item_col:
					max_item_col = len(line)

				print_lines.append(line)

		if os.path.exists("/proc/diskstats"):
			with open("/proc/diskstats", "r") as f:
				diskinfo_str = f.read()
				time_sub = time.time() * 1000 - last_time_ms["diskstats"]
				diskinfo_iter = diskinfo_re.finditer(diskinfo_str)

				for i in diskinfo_iter:
					disk_info = {}
					disk_info["name"] = i.group(2)
					disk_info["rd_ios"] = int(i.group(3))
					disk_info["rd_merges"] = int(i.group(4))
					disk_info["rd_sectors"] = int(i.group(5))
					disk_info["rd_ticks"] = int(i.group(6))
					disk_info["wr_ios"] = int(i.group(7))
					disk_info["wr_merges"] = int(i.group(8))
					disk_info["wr_sectors"] = int(i.group(9))
					disk_info["wr_ticks"] = int(i.group(10))
					disk_info["in_flight"] = int(i.group(11))
					disk_info["io_ticks"] = int(i.group(12))
					disk_info["time_in_queue"] = int(i.group(13))

					key = i.group(2)
					if key not in disk_infos_last:
						disk_infos_last[key] = disk_info
					else:
						disk_info_sub = {}
						disk_info_sub["rd_ios"] = disk_info["rd_ios"] - disk_infos_last[key]["rd_ios"]
						disk_info_sub["rd_merges"] = disk_info["rd_merges"] - disk_infos_last[key]["rd_merges"]
						disk_info_sub["rd_sectors"] = disk_info["rd_sectors"] - disk_infos_last[key]["rd_sectors"]
						disk_info_sub["rd_ticks"] = disk_info["rd_ticks"] - disk_infos_last[key]["rd_ticks"]
						disk_info_sub["wr_ios"] = disk_info["wr_ios"] - disk_infos_last[key]["wr_ios"]
						disk_info_sub["wr_merges"] = disk_info["wr_merges"] - disk_infos_last[key]["wr_merges"]
						disk_info_sub["wr_sectors"] = disk_info["wr_sectors"] - disk_infos_last[key]["wr_sectors"]
						disk_info_sub["wr_ticks"] = disk_info["wr_ticks"] - disk_infos_last[key]["wr_ticks"]
						disk_info_sub["in_flight"] = disk_info["in_flight"] - disk_infos_last[key]["in_flight"]
						disk_info_sub["io_ticks"] = disk_info["io_ticks"] - disk_infos_last[key]["io_ticks"]
						disk_info_sub["time_in_queue"] = disk_info["time_in_queue"] - disk_infos_last[key]["time_in_queue"]
						if key in disk_infos_sub:
							del(disk_infos_sub[key])

						del(disk_infos_last[key])
						disk_infos_last[key] = disk_info
						disk_infos_sub[key] = disk_info_sub
				
				for key, value in disk_infos_sub.items():
					if not disk_filter.match(key) and not disk_detal:
						continue
					disk_usage = int(value["io_ticks"] * 100 / time_sub )
					disk_read_speed = int(value["rd_sectors"] * 512 * 1000 / time_sub )
					disk_write_speed = int(value["wr_sectors"] * 512 * 1000 / time_sub )

					line = []
					line.append([{"ctrl_count" : 0, "str" : "disk"}, {"ctrl_count" : 0, "str" : ""}])
					line.append([{"ctrl_count" : 0, "str" : key}, {"ctrl_count" : 0, "str" : ""}])
					line.append([{"ctrl_count" : 0, "str" : "read:"}, {"ctrl_count" : 0, "str" : format_number(disk_read_speed)}])
					line.append([{"ctrl_count" : 0, "str" : "write:"}, {"ctrl_count" : 0, "str" : format_number(disk_write_speed)}])
					line.append([{"ctrl_count" : 0, "str" : "usage:"}, format_color(disk_usage, 90)])
					line.append([{"ctrl_count" : 0, "str" : "iop_r:"}, {"ctrl_count" : 0, "str" : format_number(value["rd_ios"])}])
					line.append([{"ctrl_count" : 0, "str" : "iop_w:"}, {"ctrl_count" : 0, "str" : format_number(value["wr_ios"])}])
					if len(line) > max_item_col:
						max_item_col = len(line)

					print_lines.append(line)
			last_time_ms["diskstats"] = time.time() * 1000

		tty_size = os.get_terminal_size()
		height = tty_size[1] - 1
		print_strs_fix = ["\033[H"]

		head_width = 5
		item_width = 13
		item_cols = int((tty_size[0] - head_width - 2) / item_width)
		if item_cols > max_item_col:
			item_cols = max_item_col

		str_format = ""
		for x in range(item_cols):
			str_format = str_format + "|{}"
		str_format = str_format + "|\n"
		item_width = int((tty_size[0] - head_width -2 - item_cols - 1) / (item_cols - 1))

		for items in print_lines:
			item_str = []
			for x in range(item_cols):
				if x >= len(items):
					if x == 0:
						item_str.append(f"{'  ':{head_width}}")
					else:
						item_str.append(f"{'':{item_width}}")
				else:
					item = items[x]
					if x == 0:
						item_str.append(f" {item[0]['str']:<{head_width}} ")
					else:
						late_str_count = item_width - len(item[0]['str']) - item[0]['ctrl_count'] + item[1]['ctrl_count']
						item_str.append(f"{item[0]['str']}{item[1]['str']:>{late_str_count}}")
			if height > 0:
				print_strs_fix.append(str_format.format(*item_str))
				height = height - 1

		# item_str = []
		# for x in range(item_cols):
		# 	if x == 0:
		# 		item_str.append(f" {str(head_width):^{head_width}} ")
		# 	else:
		# 		item_str.append(f"{str(item_width):^{item_width}}")
		# if height > 0:
		# 	print_strs_fix.append(str_format.format(*item_str))
		# 	height = height - 1

		if os.path.exists("/proc"):
			for item in os.scandir("/proc"):
				if item.is_dir():
					if process_dir_re.match(item.path):
						try:
							process_info = {}
							with open(item.path + "/stat", "r") as f:
								processinfo_str = f.read()
								time_sub = time.time() * 1000 - last_time_ms["stat"]
								processinfo_iter = processinfo_re.match(processinfo_str)
								if processinfo_iter is None:
									break;
								process_info["pid"] = int(processinfo_iter.group(1))
								process_info["comm"] = processinfo_iter.group(2)
								process_info["task_state"] = processinfo_iter.group(3)
								process_info["utime"] = int(processinfo_iter.group(14))
								process_info["stime"] = int(processinfo_iter.group(15))
								process_info["priority"] = int(processinfo_iter.group(18))
								process_info["nice"] = int(processinfo_iter.group(19))
								process_info["rss"] = int(processinfo_iter.group(24)) * resource.getpagesize()
								process_info["task_cpu"] = int(processinfo_iter.group(39))
								process_info["task_rt_priority"] = int(processinfo_iter.group(40))
								process_info["task_policy"] = int(processinfo_iter.group(41))
								process_info["blio_ticks"] = int(processinfo_iter.group(42))
								key = processinfo_iter.group(1)

							with open(item.path + "/status", "r") as f:
								processinfo_str = f.read()
								processinfo_iter = processstatus_re.search(processinfo_str)
								if processinfo_iter is None:
									break;
								process_info["userid"] = processinfo_iter.group(1)

							if key not in process_infos_last:
								process_infos_last[key] = process_info
							else:
								process_info_sub = {}
								process_info_sub["pid"] = process_info["pid"]
								process_info_sub["comm"] = process_info["comm"]
								if os.path.exists(item.path + "/cmdline"):
									with open(item.path + "/cmdline", "r") as f_cmd:
										 cmdline = f_cmd.read()
										 if cmdline != "":
										 	process_info_sub["comm"] = cmdline

								process_info_sub["task_state"] = process_info["task_state"]
								process_info_sub["userid"] = process_info["userid"]
								process_info_sub["utime"] = process_info["utime"] - process_infos_last[key]["utime"]
								process_info_sub["stime"] = process_info["stime"] - process_infos_last[key]["stime"]
								m, s = divmod((process_info["utime"] + process_info["stime"]) / 100, 60)
								h, m = divmod(m, 60)
								process_info_sub["time_sum"] = f"{h:.0f}:{m:02.0f}:{s:02.0f}"
								process_info_sub["time"] = process_info_sub["utime"] + process_info_sub["stime"]
								process_info_sub["cpu_usage"] = process_info_sub["time"] * 1000 / time_sub
								
								if total_mem != 0:
									process_info_sub["mem_usage"] = process_info["rss"] * 100 / total_mem
								else:
									process_info_sub["mem_usage"] = 0

								process_info_sub["priority"] = process_info["priority"]
								process_info_sub["nice"] = process_info["nice"]
								process_info_sub["rss"] = process_info["rss"]
								process_info_sub["task_cpu"] = process_info["task_cpu"]
								process_info_sub["task_rt_priority"] = process_info["task_rt_priority"]
								process_info_sub["task_policy"] = process_info["task_policy"]
								process_info_sub["blio_ticks"] = process_info["blio_ticks"] - process_infos_last[key]["blio_ticks"]
								
								if key in process_infos_sub:
									del(process_infos_sub[key])

								del(process_infos_last[key])
								process_infos_last[key] = process_info
								process_infos_sub[key] = process_info_sub
						except Exception as e:
							pass
						finally:
							pass
			last_time_ms["stat"] = time.time() * 1000

			col = tty_size[0] - 72
			if height > 0:
				print_strs_fix.append(f"\033[7m{'PID':^10}|{'USER':^14}|{'CORE':^4}|{'MEM':^8}|{'%MEM':>5}|{'%CPU':^6}|{'TIME':^10}|{'STATE':^5}| {'COMMAND':<{col}}\033[0m"[:tty_size[0] + 8] + "\n")
				height = height - 1

			process_info_sort = sorted(process_infos_sub.values(), key=lambda d: d["time"], reverse=True)
			for item in process_info_sort:
				if height > 0:
					if item['userid'] in userid_to_name:
						pid_user = userid_to_name[item['userid']]
					else:
						pid_user = item['userid']
					print_strs_fix.append(f" {item['pid']:>9}   {pid_user:<12} {item['task_cpu']:>3} {format_number(item['rss']):>7}   {item['mem_usage']:>4.1f}% {item['cpu_usage']:>5.1f}% {item['time_sum']:^10} {item['task_state']:^5}  {item['comm']:<{col}}"[:tty_size[0]] + "\n")
					height = height - 1

		print("".join(print_strs_fix), end="", flush=True)
		del(print_lines)
		del(print_strs_fix)
		# time.sleep(1)
		check_input(time_interval)

def int_handler(signum, frame):
	global exit
	exit = True

if __name__ == '__main__':
	sys_name = platform.system()
	if sys_name == "Linux":
		signal.signal(signal.SIGINT, int_handler)
		parser = argparse.ArgumentParser(description='Process some integers.')
		parser.add_argument('-c', '--cpu-detal', dest = "cpu_detal", default=False,
			action = "store_true", required = False, help='show every cpu core.')
		parser.add_argument('-d', '--disk-detal', dest = "disk_detal", default=False,
			action = "store_true", required = False, help='show every part.')
		parser.add_argument('-t', '--time-interval', dest = "time_interval", type=float, default=1,
			required = False, help='refresh frequency')
		args = parser.parse_args()
		cpu_detal = args.cpu_detal
		disk_detal = args.disk_detal
		time_interval = args.time_interval
		run()
	else:
		print("Must run on Linux!!!")
