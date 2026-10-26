; Installateur de Bilan santé PC (Inno Setup 6), fabriqué par build.bat :
;   ISCC.exe /DVersion=X.Y.Z installateur.iss   ->   dist\BilanSantePC-Installation-vX.Y.Z.exe
;
; Installation pour l'utilisateur seul, sans droits d'administrateur : %LOCALAPPDATA%\Programs\BilanSantePC.
; Les mises à jour de l'application (modules/mise_a_jour.py) lancent ce même installateur, sans questions :
;   /SILENT /SUPPRESSMSGBOXES /NORESTART /DIR=<dossier de l'application> /ATTENDRE=<pid de l'application>
; Il attend alors que l'application se ferme, la remplace dans son dossier, puis la rouvre.
; L'ancienne version est d'abord mise de côté (.ancienne-version, effacé au lancement suivant) : rien d'elle ne reste
; mêlé à la nouvelle, et elle est remise en place si l'installation échoue.

#ifndef Version
  #error Version manquante : ISCC.exe /DVersion=X.Y.Z installateur.iss
#endif

[Setup]
AppId={{2381BEDB-4D02-4535-9F35-EF9EA4E0606B}
AppName=Bilan santé PC
AppVersion={#Version}
AppVerName=Bilan santé PC {#Version}
AppPublisher=MonsieurPlot1
AppPublisherURL=https://github.com/MonsieurPlot1/bilan-sante-pc
VersionInfoVersion={#Version}
DefaultDirName={autopf}\BilanSantePC
PrivilegesRequired=lowest
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern dynamic
SetupIconFile=assets\icon.ico
UninstallDisplayName=Bilan santé PC
UninstallDisplayIcon={app}\BilanSantePC.exe
OutputDir=dist
OutputBaseFilename=BilanSantePC-Installation-v{#Version}
Compression=lzma2/max
SolidCompression=yes

[Languages]
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "bureau"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\BilanSantePC\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Bilan santé PC"; Filename: "{app}\BilanSantePC.exe"
Name: "{autodesktop}\Bilan santé PC"; Filename: "{app}\BilanSantePC.exe"; Tasks: bureau

[Run]
Filename: "{app}\BilanSantePC.exe"; Description: "Ouvrir Bilan santé PC"; Flags: nowait postinstall skipifsilent
; Mise à jour depuis l'application : elle se rouvre et dit qu'elle est à jour.
Filename: "{app}\BilanSantePC.exe"; Parameters: "--mise-a-jour-faite"; Flags: nowait; Check: EnMiseAJour

[UninstallDelete]
; Restes éventuels d'une mise à jour. L'historique et les réglages (%LOCALAPPDATA%\BilanSantePC) sont gardés.
Type: filesandordirs; Name: "{app}\.mise-a-jour"
Type: filesandordirs; Name: "{app}\.ancienne-version"

[Code]
const
  SYNCHRONIZE = $00100000;
  ATTENTE_FERMETURE = 120000; // millisecondes : l'application finit d'abord une analyse en cours
  ATTENTE_REUSSIE = 0;        // WAIT_OBJECT_0

function OpenProcess(Acces: Longword; Heritage: Bool; Pid: Longword): Longword;
external 'OpenProcess@kernel32.dll stdcall';
function WaitForSingleObject(Processus, Delai: Longword): Longword;
external 'WaitForSingleObject@kernel32.dll stdcall';
function CloseHandle(Processus: Longword): Bool;
external 'CloseHandle@kernel32.dll stdcall';

var
  Installee, MiseDeCote: Boolean;

// Lancé par le bouton « Mettre à jour » de l'application (paramètre /ATTENDRE=<pid>).
function EnMiseAJour: Boolean;
begin
  Result := ExpandConstant('{param:ATTENDRE|0}') <> '0';
end;

// Avant tout : attend que l'application se ferme, pour pouvoir remplacer ses fichiers.
function InitializeSetup: Boolean;
var
  Pid, Processus: Longword;
begin
  Result := True;
  Pid := StrToIntDef(ExpandConstant('{param:ATTENDRE|0}'), 0);
  if Pid = 0 then
    Exit;
  Processus := OpenProcess(SYNCHRONIZE, False, Pid);
  if Processus = 0 then
    Exit; // déjà fermée
  if WaitForSingleObject(Processus, ATTENTE_FERMETURE) <> ATTENTE_REUSSIE then
  begin
    Log('L''application ne s''est pas fermée : installation abandonnée');
    Result := False;
  end;
  CloseHandle(Processus);
end;

function DansApplication(Nom: String): String;
begin
  Result := ExpandConstant('{app}\') + Nom;
end;

function MisDeCote(Nom: String): String;
begin
  Result := DansApplication('.ancienne-version\' + Nom);
end;

// Rend ce qui a été mis de côté, et seulement cela (le dossier était vide avant).
procedure RemettreAncienne;
begin
  if DirExists(MisDeCote('_internal')) then
  begin
    DelTree(DansApplication('_internal'), True, True, True);
    RenameFile(MisDeCote('_internal'), DansApplication('_internal'));
  end;
  if FileExists(MisDeCote('BilanSantePC.exe')) then
  begin
    DeleteFile(DansApplication('BilanSantePC.exe'));
    RenameFile(MisDeCote('BilanSantePC.exe'), DansApplication('BilanSantePC.exe'));
  end;
end;

// Juste avant de copier : l'ancienne version (si elle est là) part de côté, d'un simple renommage.
function PrepareToInstall(var RedemarrageNecessaire: Boolean): String;
begin
  Result := '';
  if not FileExists(DansApplication('BilanSantePC.exe')) then
    Exit; // première installation
  DelTree(DansApplication('.ancienne-version'), True, True, True); // reste d'une mise à jour précédente
  if DirExists(DansApplication('.ancienne-version'))
     or not ForceDirectories(DansApplication('.ancienne-version')) then
    Result := 'Bilan santé PC est peut-être encore ouvert : ferme-le, puis relance l''installation.'
  else
  begin
    MiseDeCote := True;
    if (DirExists(DansApplication('_internal'))
        and not RenameFile(DansApplication('_internal'), MisDeCote('_internal')))
       or not RenameFile(DansApplication('BilanSantePC.exe'), MisDeCote('BilanSantePC.exe')) then
    begin
      RemettreAncienne;
      MiseDeCote := False;
      Result := 'Bilan santé PC est peut-être encore ouvert : ferme-le, puis relance l''installation.';
    end;
  end;
end;

procedure CurStepChanged(Etape: TSetupStep);
begin
  if Etape = ssPostInstall then
    Installee := True;
end;

// Échec : l'ancienne version revient, et une mise à jour rouvre quand même l'application pour le signaler.
procedure DeinitializeSetup;
var
  Code: Integer;
begin
  if MiseDeCote and not Installee then
    RemettreAncienne;
  if EnMiseAJour and not Installee then
    Exec(ExpandConstant('{param:DIR|}') + '\BilanSantePC.exe', '--mise-a-jour-ratee', '', SW_SHOW, ewNoWait, Code);
end;
