$json = Get-Content 'D:\Proyectos\AI_OSAP\osap-storage\pending_composers.json' -Raw | ConvertFrom-Json
$result = @()
for($i=240; $i -le 359; $i++) {
    $result += $json[$i].name
}
$result | Out-File 'D:\Proyectos\AI_OSAP\osap-storage\batch3_names.txt'
