#first step unzipping the file:
unzip Raman-mac-style.zip

#copy it to the plymouth themes section:
sudo cp -r ... /usr/share/plymouth/theme/.

#find out if your  theme is recognised or not
sudo plymouth-set-default-theme -l

#set it as default theme
sudo plymouth-set-default-theme -R Raman_OS_style

#Make adjustments to the initial ramdisk:
Please open the file "/etc/mkinitcpio.conf" in the terminal. Here, too, I'm using nano again:
sudo nano /etc/mkinitcpio.conf
For MODULES=( ), enter one of the following values inside the parentheses:
Intel GPU: i915
Newer Intel GPU: i915 xe
Newer AMD GPU: amdgpu
Older AMD GPU: radeon
Nvidia GPU (open source driver): nouveau
Nvidia GPU (proprietary driver), all 4 values are needed: nvidia nvidia_modeset nvidia_drm nvidia_uvm
For HOOKS= (...), enter "plymouth." It's best to put it right after "base." For example:
HOOKS=(base udev plymouth systemd ...) 
-----------------Note: don't uncomment the HOOKs section at the first section of the fle the actual HOOKs=() IS AT THE end of the file, there are multiple hooks ---------------------
Then save the file by pressing "Ctrl+S" and close the editor by pressing "Ctrl+X"
Then rebuild the initial ramdisk:
sudo mkinitcpio -P



#Customize the Bootloader if your computer is dualboot and you changed the boot config previously then it is enought
Open the file "/etc/default/grub" in the terminal using your preferred text editor. For this example, I'm using nano:
sudo nano /etc/default/grub
In the file, look for a line that begins with:
GRUB_CMDLINE_LINUX_DEFAULT=
Then use the arrow keys to navigate to that line.
Now add the following parameters inside the quotation marks:
quiet splash loglevel=3
Then look for this line:
#GRUB_GFXMODE=
Remove the # at the beginning of the line, and enter your monitor's resolution after the = symbol. If a resolution is already listed there, delete it and enter your values here. Here are some examples:
For Full-HD (1080p): GRUB_GFXMODE=1920x1080
For 2,5K (1440p): GRUB_GFXMODE=2560x1440
For 4K (4K): GRUB_GFXMODE=3840x2160
Then press "Ctrl+S" and "Ctrl+X" to save the file and close the text editor.
Then enter the following command to reload the GRUB configuration:
sudo grub-mkconfig -o /boot/grub/grub.cfg


#the most important thing:      ---Note: last step-------------------

if the file linux.conf is there then make it:
sudo nano /etc/cmdline.d/linux.conf

then write this things in the file:                   ------------- your can get the desired ssid with the command "lsblk -f" the id of the root partition which will be denoted by "/" at the column Mountpoint------------------
root=uuid='your uuid' rw quiet splash loglevel=3 systemd.show_status=false

save the file and exit
again regenerate the ramdisk:
sudo mkinitcpio -P

After that, you can restart the system.



for any diagnosis follow the log at :
/var/log/boot.log
