#!/usr/bin/env python
import re
import subprocess
import os
import sys

#################################################
##   Dwarf parsing...
#################################################

dwarfArray = []
symTab = {}

def parseSymbolTable(elfFileName):
	global symTab	
	path = os.path.dirname(os.path.abspath(__file__))
	ps = subprocess.Popen(path + "\\objdump -t " + elfFileName, stdout=subprocess.PIPE,stderr=subprocess.STDOUT)

	symTabStream = ps.communicate()[0]

        # Load symbols out of symfile generated by objdump
        lengths = {"":""}
        for line in symTabStream:
                match = re.match('(.*?)\ .*\t(.*?)\ (.*)', line)
                if hasattr(match,'group'):
                        symTab[match.group(3)] = match.group(1)
                        lengths[match.group(3)] = match.group(2)


def parseDwarfOutput(elfFileName):
	path = os.path.dirname(os.path.abspath(__file__))
	ps = subprocess.Popen(path + "\\objdump --dwarf=info " + elfFileName, stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
	dwarf = ps.communicate()[0]

	deepth = 0
	addr = 0
	for line in dwarf.split('\n'):
		if line.strip().startswith("<"):
			new = 0
			first = re.match('.*<([0-9a-f]+)>(.*)',line)
			if first is None:
				continue
			addr = first.group(1)
			tuple = first.group(2)
			second = re.match('.*<([0-9a-f]+)><([0-9a-f]+)>:(.*)',line)
			if second is not None:
				new = 1
				deepth = second.group(1)
				addr = second.group(2)
				tuple = second.group(3)
			tupleArray = tuple.split(':',1)
			dwarfArray.append({"address" : int(addr, 16), "deepth" : deepth, "name" : tupleArray[0].strip(), "value" : tupleArray[1].strip(), "new" : new})


def getDwarfType(typeAddress):
	typeFound = 0
	retVal = {}
	for i in range(len(dwarfArray)):
		if (dwarfArray[i]["address"] == typeAddress):
			typeFound = i
			while(i < len(dwarfArray)):
				if dwarfArray[i]["name"] == "DW_AT_name":
					retVal["name"] = dwarfArray[i]["value"]
				elif dwarfArray[i]["name"] == "DW_AT_type":
					dummy = getDwarfType(int(dwarfArray[i]["value"][1:-1],0))
					retVal["type"] = dummy[1]
				elif dwarfArray[i]["name"] == "DW_AT_byte_size":
					retVal["size"] = dwarfArray[i]["value"]
				elif dwarfArray[i]["name"] == "DW_AT_data_member_location":
					match = re.match('.*DW_OP_plus_uconst:(.*)\)',dwarfArray[i]["value"])
					if match is not None:
						retVal["offset"] = (match.group(1))
					else:
						print ("")
				i = i+1;
				countElements = 0
				while i < len(dwarfArray) and dwarfArray[i]["new"] == 1 and dwarfArray[i]["deepth"] > dwarfArray[typeFound]["deepth"]:
					dummy = getDwarfType(dwarfArray[i]["address"])
					i = dummy[0]
					if "name" in dummy[1]:
						retVal["%d" % (countElements)] = dummy[1]
						countElements += 1
				if i < len(dwarfArray) and dwarfArray[i]["new"] == 1 and dwarfArray[i]["deepth"] <= dwarfArray[typeFound]["deepth"]:
					retVal["countElements"] = countElements
					break
			break
	return i, retVal

def getDwarfVar(name):
	foundArray = None
	address = ""
	struct = 0
	for i in range(len(dwarfArray)):
		if dwarfArray[i]["name"] == "DW_AT_name" and dwarfArray[i]["value"] == name:
			foundArray = i
			while i < len(dwarfArray) and dwarfArray[i]["new"] != 1:
				if dwarfArray[i]["name"] == "DW_AT_location":
					struct = 1
					match = re.match(".*\(DW_OP_addr\:\ *([0-9a-f]+)\).*", dwarfArray[i]["value"])
					if match is not None:
						address = match.group(1)
					break
				i += 1
			#print name + " ",
			break
	if foundArray is not None:
		typeAddr = int(dwarfArray[foundArray+1]["value"][1:-1],0)
		type = getDwarfType(typeAddr)
		if struct == 1:
			type[1]["struct"] = 1
		type[1]["address"] = address
		return type[1]


def printDwarfVar(FoundType, baseAddr, name):
	if "name" in FoundType:
		name = FoundType["name"]
	if "type" in FoundType:
		print FoundType["type"]["name"] + " " + name + ";\t/* " + FoundType["type"]["size"] + ", at 0x",
		if "address" in FoundType:
			print FoundType["address"] + " */"
		else:
			print baseAddr + " + " + FoundType["offset"] + " */"
	elif "struct" in FoundType:
		print "struct " + name + " /* " + FoundType["size"] + ", at 0x" + FoundType["address"] +  " */"
		print "{"
		for i in range(0, FoundType["countElements"]):
			printDwarfVar(FoundType["%d" % (i)], FoundType["address"], name)
		print "}"


def findAddress(name, useSymbolTable=False):
	if useSymbolTable == True:
		global symTab
		if name in symTab:
			return "0x%x" % int(symTab[name], 16)
		else:
			print "name: " + name + " not found "
			return "0"
		
	else:
		if "." in name:
			structPath = name.split('.')
			FoundVar = getDwarfVar(structPath[0])
			address = int(FoundVar["address"], 16)
			for subLevel in structPath[1:]:
				for i in range(0, FoundVar["countElements"]):
					if subLevel == FoundVar["%d" % (i)]["name"]:
						address += int(FoundVar["%d" % (i)]["offset"], 16)
					break
			return "0x%x" % (address)
		else:
			FoundVar = getDwarfVar(name)
			if "address" in FoundVar:
	#			print "name: " + name + " address: " + FoundVar["address"]
				return "0x%x" % int(FoundVar["address"], 16)
			else:
				print "name: " + name + " not found "
				return "0"


#################################################
##   A2L parsing...
#################################################


a2lInput = ""
trenner = [' ','[',']','{','}','(',')',',',';','=','\r','\n']
def getNextToken(pos, length):
	global a2lInput
	while pos < length:
		if a2lInput[pos:pos+2] == "/*":
			pos = pos + 2
			startpos = pos
			while pos < length and not a2lInput[pos:pos+2] == '*/':
				pos = pos + 1
			pos = pos+2
		elif a2lInput[pos] == '"':
			pos = pos + 1
			startpos = pos
			while pos < length and not a2lInput[pos] == '"':
				pos = pos + 1
			return [pos+1, "STRING", a2lInput[startpos:pos]]
		elif a2lInput[pos:pos+6] == "/begin":
			return [pos+6, "BEGIN", ""]
		elif a2lInput[pos:pos+4] == "/end":
			return [pos+4, "END", ""]
		elif a2lInput[pos].isspace() or a2lInput[pos] == '\n':
			pos = pos + 1
		else:
			startpos = pos
			while pos < length and not a2lInput[pos] in trenner:
				pos = pos + 1
			return [pos, "OUTLINE", a2lInput[startpos:pos]]
	return [pos,"END", ""]

def updateA2L(fileName, useSymbolTable=False):
	a2lInputFile = open(fileName, "r")
	global a2lInput
	a2lInput = a2lInputFile.read()
	length = len(a2lInput)
	output = ""

	pos = 0
	lastPos = 0
	ignore = 0
	while pos < length:
		[pos, Token, outline] = getNextToken(pos, length)
		if  pos < length:
			[pos2, Token2, outline2] = getNextToken(pos, length)
		else:
			pos2 = length
			Token2 = ""
			outline2 = ""
		if Token == "BEGIN":
			[pos, tt, blockname] = getNextToken(pos, length)
			if blockname == "CHARACTERISTIC":
				output += a2lInput[lastPos:pos]
				[pos, tt, blockname] = getNextToken(pos, length)
				name = blockname
				[pos, tt, blockname] = getNextToken(pos, length)
				Long = blockname
				[pos, tt, blockname] = getNextToken(pos, length)
				Type = blockname
				[pos, tt, blockname] = getNextToken(pos, length)
				Addr = blockname
				lastPos = pos
				output += "\n" + name + "\n\"" + Long + "\"\n" + Type + "\n " + findAddress(name, useSymbolTable) + "\n"
			elif blockname == "MEASUREMENT":
				output += a2lInput[lastPos:pos]
				[pos, tt, blockname] = getNextToken(pos, length)
				name = blockname
				[pos, tt, blockname] = getNextToken(pos, length)
				Long = blockname
				output += "\n" + name + "\n\"" + Long + "\"\n"
				lastPos = pos
				while blockname != "ECU_ADDRESS":
					[pos, tt, blockname] = getNextToken(pos, length)
					output += a2lInput[lastPos:pos]
					lastPos = pos
				[pos, tt, blockname] = getNextToken(pos, length)
				lastPos = pos
				output += "\t " + findAddress(name, useSymbolTable) + "\n"
		else:
			pass
		output += a2lInput[lastPos:pos]
		lastPos = pos
	return output



from optparse import OptionParser

usage = """

%prog [options]  elf-file a2l-input a2l-output
"""

parser = OptionParser(usage=usage)
#parser.add_option("-d", "--debug",
#                  dest="debug", default=False,
#                  help="print debug messages to stdout")
#parser.add_option("", "--dbcCharset", 
#                  dest="dbcCharset", default="iso-8859-1",
#                  help="Charset of Comments in dbc, maybe utf-8")
parser.add_option("-s", "--useSymbolTable", action="store_false",
                  dest="useSymbolTable", default=False,
                  help="use symboltable of elf-file (much faster, but without support for structs)")
(cmdlineOptions, args) = parser.parse_args()


if len(args) < 2:
    parser.print_help()
    sys.exit(1)

print "parsing elf file ... ",
if cmdlineOptions.useSymbolTable == True:
	pass
else:
	parseDwarfOutput(args[0])
print "done"

newA2l = updateA2L(args[1], cmdlineOptions.useSymbolTable)
newA2lFile = open(args[2], "w")
newA2lFile.write(newA2l)
newA2lFile.close()
