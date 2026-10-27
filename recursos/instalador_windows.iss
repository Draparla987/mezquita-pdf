; Instalador de Mezquita PDF para Windows (Inno Setup 6).
;   iscc /DVersion=2.7.0 recursos\instalador_windows.iss   →  dist\MezquitaPDF-windows.exe
; Se instala solo para el usuario (sin pedir permisos de administrador): así las
; actualizaciones automáticas pueden ejecutarlo en silencio.

#ifndef Version
  #define Version "0.0.0"
#endif
; Ediciones con logotipos para la marca de agua del sello (p. ej. la del IMIBIC):
;   /DMarcas=carpeta_con_los_png /DMarcaPorDefecto=IMIBIC /DSalida=MezquitaPDF-IMIBIC-windows
; Los logotipos van a la carpeta de datos del usuario, así que las actualizaciones normales no los tocan.
#ifndef Salida
  #define Salida "MezquitaPDF-windows"
#endif

[Setup]
AppId={{6E0B3C2A-6F1D-4C8E-9C7A-3F2D5B8E1A47}
AppName=Mezquita PDF
AppVersion={#Version}
AppVerName=Mezquita PDF {#Version}
AppPublisher=Mezquita PDF
AppPublisherURL=https://github.com/Draparla987/mezquita-pdf
AppUpdatesURL=https://github.com/Draparla987/mezquita-pdf/releases
VersionInfoVersion={#Version}
DefaultDirName={autopf}\Mezquita PDF
DefaultGroupName=Mezquita PDF
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename={#Salida}
SetupIconFile=icono.ico
UninstallDisplayIcon={app}\Mezquita PDF.exe
UninstallDisplayName=Mezquita PDF
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
ChangesAssociations=yes
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "escritorio"; Description: "Crear un acceso directo en el escritorio"; Flags: unchecked

[Files]
Source: "..\dist\Mezquita PDF\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
#ifdef Marcas
Source: "{#Marcas}\*.png"; DestDir: "{userappdata}\MezquitaPDF\marcas"; Flags: onlyifdoesntexist uninsneveruninstall
#endif

[InstallDelete]
; Restos de la versión anterior (las bibliotecas cambian de nombre entre versiones)
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\Mezquita PDF"; Filename: "{app}\Mezquita PDF.exe"; AppUserModelID: "MezquitaPDF.App"
Name: "{autodesktop}\Mezquita PDF"; Filename: "{app}\Mezquita PDF.exe"; Tasks: escritorio; AppUserModelID: "MezquitaPDF.App"

[Registry]
; Extensión de Chrome «Firmar con Mezquita PDF»: la app escribe el manifiesto al abrirse; aquí se
; registra para que el desinstalador lo quite
Root: HKCU; Subkey: "Software\Google\Chrome\NativeMessagingHosts\es.mezquitapdf.chrome"; ValueType: string; ValueName: ""; ValueData: "{userappdata}\MezquitaPDF\chrome\es.mezquitapdf.chrome.json"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Microsoft\Edge\NativeMessagingHosts\es.mezquitapdf.chrome"; ValueType: string; ValueName: ""; ValueData: "{userappdata}\MezquitaPDF\chrome\es.mezquitapdf.chrome.json"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\BraveSoftware\Brave-Browser\NativeMessagingHosts\es.mezquitapdf.chrome"; ValueType: string; ValueName: ""; ValueData: "{userappdata}\MezquitaPDF\chrome\es.mezquitapdf.chrome.json"; Flags: uninsdeletekey
#ifdef MarcaPorDefecto
; Marca de agua elegida de entrada (solo si el usuario no ha elegido otra)
Root: HKCU; Subkey: "Software\MezquitaPDF\Mezquita PDF\firma"; ValueType: string; ValueName: "marca"; ValueData: "{#MarcaPorDefecto}"; Flags: createvalueifdoesntexist
#endif
; Tipo de documento propio y «Abrir con» para los .pdf (no cambia la app predeterminada:
; eso lo decide el usuario en Configuración, como exige Windows)
Root: HKA; Subkey: "Software\Classes\MezquitaPDF.Documento"; ValueType: string; ValueName: ""; ValueData: "Documento PDF"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\MezquitaPDF.Documento\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\Mezquita PDF.exe,0"
Root: HKA; Subkey: "Software\Classes\MezquitaPDF.Documento\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\Mezquita PDF.exe"" ""%1"""
Root: HKA; Subkey: "Software\Classes\.pdf\OpenWithProgids"; ValueType: string; ValueName: "MezquitaPDF.Documento"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Applications\Mezquita PDF.exe"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "Mezquita PDF"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Applications\Mezquita PDF.exe\SupportedTypes"; ValueType: string; ValueName: ".pdf"; ValueData: ""
; Para que aparezca en Configuración → Aplicaciones predeterminadas
Root: HKA; Subkey: "Software\Mezquita PDF\Capabilities"; ValueType: string; ValueName: "ApplicationName"; ValueData: "Mezquita PDF"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Mezquita PDF\Capabilities"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "Visor y editor de PDF con firma electrónica"
Root: HKA; Subkey: "Software\Mezquita PDF\Capabilities\FileAssociations"; ValueType: string; ValueName: ".pdf"; ValueData: "MezquitaPDF.Documento"
Root: HKA; Subkey: "Software\RegisteredApplications"; ValueType: string; ValueName: "Mezquita PDF"; ValueData: "Software\Mezquita PDF\Capabilities"; Flags: uninsdeletevalue

[Run]
Filename: "{app}\Mezquita PDF.exe"; Description: "Abrir Mezquita PDF"; Flags: nowait postinstall skipifsilent
