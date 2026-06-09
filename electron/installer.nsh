; Tue le processus MusicDL avant installation / désinstallation
!macro customInstall
  ExecWait '$SYSDIR\taskkill.exe /F /IM "MusicDL.exe" /T'
  Sleep 800
!macroend

!macro customUnInstall
  ExecWait '$SYSDIR\taskkill.exe /F /IM "MusicDL.exe" /T'
  Sleep 500
!macroend
