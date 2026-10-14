#go to the place /usr/share/systemd/bootctl/.
#find the image splash-arch.bmp
#change it with the image provided here. 

2.Edit your mkinitcpio preset:
    Where the image is configured.The configuration that tells your system to embed this image into your kernel is located in your mkinitcpio presets. Open it with root privileges:
    '''bash
        sudo nano /etc/mkinitcpio.d/linux.preset
    '''
    (If you use a different kernel like linux-zen, edit linux-zen.preset instead).
3.Modify the splash parameter:
    Disable or customize it.Look for a line that starts with default_options=.
    '''edit: 
    Plaintextdefault_options="--splash=/usr/share/systemd/bootctl/splash-raman.bmp"
    '''
OPTIONAL:
    To disable the banner entirely:
    Remove the --splash parameter from the quotes, leaving it like default_options="" (or whatever other flags you might have in there, just remove the splash part).To use your own custom logo:Change the path to point to a custom .bmp file on your system. (Note: it must be a Windows BMP format image, not a PNG or JPG).

4.Rebuild your UKI:
    Bake the changes into the kernel.Because the splash screen lives inside the .efi executable, you must regenerate it for the changes to apply. 
    '''bash:
        sudo mkinitcpio -P
    ''' 


done you are ready to go

