# rEFInd rich black theme

![screenshot](screenshot.png)

## Installation
1. take backup the current refind.conf file with the command:
    ```badh
    sudo mv /boot/EFI/refind/refind.conf /boot/EFI/refind/refind.conf.back
    ```
    then take the given reind.conf file to the same directory
    ```bash 
    sudo mv redind.conf /boot/EFI/refind/.
    ```

2. Copy the theme to the rEFInd directory. This is usually `/boot/EFI/refind/`.

   ```bash
   sudo cp -r raman-theme /boot/EFI/refind/
   ```

3. To adjust icon size and font size edit `theme.conf`.

   ```bash
   sudo nano /boot/EFI/refind/refind-theme/theme.conf
   ```

4. To enable the theme add `include raman-theme/theme.conf` at the end of `refind.conf`.

   ```bash
   sudo nano /boot/EFI/refind/refind.conf
   ```
5. replace the icon folder at the /boot/EFI/reind/icons with the icon file provided here

you may follow the other steps:
```bash
menuentry "Arch Linux" {
   icon /EFI/refind/refind-theme/icons/os_arch.png
   loader /vmlinuz-linux
   initrd /initramfs-linux.img
   options "rw root=UUID=[YOUR UUID] loglevel=3"
}

menuentry "Windows" {
   icon /EFI/refind/refind-theme/icons/os_win.png
   loader /EFI/Microsoft/Boot/bootmgfw.efi
}
```

[rEFInd](http://www.rodsbooks.com/refind/) The official rEFInd website
