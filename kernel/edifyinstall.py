#!/usr/bin/python
"""
This is a special python module that will be exec'd
when it is time to install the kernel loading code
into the edify script

Here is where we implement the Anykernel functionality.
The build system will make the 2708+ kernel the primary
here we need to make patches for the ebi0/ebi1 kernels 
against the 2708 base; and inject the patches and logic 
into the update.zip
"""

#
# Copyright (C) 2011 ezterry3@gmail.com 
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Note two modules are preloaded into global space
# common (build/tools/releasetools/common.py)
# edify_generator (build/tools/releasetools/edify_generator.py)
#
# We must implement a function of the following template
# make_boot_install(script,boot_img,input_zip,output_zip)
#
# This will be called when it it time to update the edify script in script

import os
import os.path
import tempfile
import shutil


def IsSymlink(info):
    """Return true if the zipfile.ZipInfo object passed in represents a
       symlink."""
    # as defined in build/tools/releasetools/ota_from_target_files
    return (info.external_attr >> 16) == 0120777

def unzip_boot_files(input_zip,output_path):
    files=filter(lambda f: f[:4]=='BOOT',input_zip.namelist())
    for f in files:
        outfile=os.path.join(output_path,f[4+len(os.path.sep):])
        
        #check the dir exists
        outdir =os.path.dirname(outfile)
        if(not os.path.isdir(outdir)):
            os.makedirs(outdir)
        #extract the file
        if(os.path.basename(outfile) != ""):
            if(IsSymlink(input_zip.getinfo(f))):
                #we have a symlink
                os.symlink(input_zip.read(f),outfile)
            else:
                #just create the output file
                fp=open(outfile,'wb')
                fp.write(input_zip.read(f))
                fp.close()

def generate_checksys(output_zip):
    checksys  = \
"""#!/sbin/sh
#
# Find system information based on the kernel command line and populate 
# nfo.prop

baseband=`awk '{m=match($0,/androidboot.baseband=([0-9a-zA-Z\.]*)/) ; print(substr($0,RSTART+21,RLENGTH-21))}' < /proc/cmdline`
bootloader=`awk '{m=match($0,/androidboot.bootloader=([0-9a-zA-Z\.]*)/) ; print(substr($0,RSTART+23,RLENGTH-23))}' < /proc/cmdline`
radioseries=`echo $baseband | awk '{print(substr($0,0,4))}'`
custommtd=`awk '/mtdparts/ {print("CustomMTD")}' < /proc/cmdline`
smisize=`awk '{m=match($0,/smisize=([0-9a-zA-Z\.]*)/) ; print(substr($0,RSTART+8,RLENGTH-8))}' < /proc/cmdline`
board=`cat /proc/cpuinfo  | grep Hardware | awk '{print $3}'`

#write out a prop file for the updater script to read
echo "baseband=$baseband" > /tmp/nfo.prop
echo "bootloader=$bootloader" >> /tmp/nfo.prop
echo "radioseries=$radioseries" >> /tmp/nfo.prop
echo "custommtd=$custommtd" >> /tmp/nfo.prop
echo "smisize=$smisize" >> /tmp/nfo.prop
echo "sysboard=$board" >> /tmp/nfo.prop
"""
    common.ZipWriteStr(output_zip,"checksys.sh",checksys)


def make_boot_install(script,boot_img,input_zip,output_zip):
    android_root=os.getenv("ANDROID_BUILD_TOP")
    temp_root=tempfile.mkdtemp(suffix="autokernel")


    #GENERATE EBI1 boot.img
    unzip_boot_files(input_zip,os.path.join(temp_root,"ebi1_BOOT"))
    shutil.copy( os.path.join(android_root,
                   "device","htc","dream-sapphire","kernel","6355-zImage"),
                 os.path.join(temp_root,"ebi1_BOOT","kernel"))
    
    fp=open(os.path.join(temp_root,"ebi1_BOOT","base"),'w')
    fp.write("0x19200000")
    fp.close()

    ebi1_boot_img = common.File("ebi1_boot.img",
                       common.BuildBootableImage(
                         os.path.join(temp_root,"ebi1_BOOT")))
    
    common.ZipWriteStr(output_zip,"kernel/6355-boot.img",ebi1_boot_img.data)

    #add in checksys.sh
    generate_checksys(output_zip)
    
    #add eddify
    script.ShowProgress(0.2, 0)
    script.ShowProgress(0.2, 10)
    script.RunBackup("restore")
    script.AppendExtra("""

#check the system information of the system we are installing on
package_extract_file("checksys.sh","/tmp/checksys.sh");
set_perm(0,0,755,"/tmp/checksys.sh");
run_program("/tmp/checksys.sh");

#determine if we need to patch a boot image
if file_getprop("/tmp/nfo.prop","radioseries") == "6.35"
then 
    #EBI1 kernel needed
    ui_print("Extracting EBI1 patch");
    package_extract_file("kernel/6355-boot.img","/tmp/boot.img");
endif;
## TODO ADD AUTO CUSTOM-MTD logic to /tmp/boot.img here ##
ui_print("Write boot.img");
assert(write_raw_image("/tmp/boot.img","boot"));
delete("/tmp/checksys.sh","/tmp/boot.img");

#END INSTALL boot.img

""")
    #clean up temporary files
    shutil.rmtree(temp_root,ignore_errors=True)
