# Sign goya_bar.sys with test certificate
$signtool = Get-ChildItem 'C:\Program Files (x86)\Windows Kits\10\bin' -Recurse -Filter 'signtool.exe' | Where-Object { $_.FullName -match 'x64' } | Select-Object -Last 1
Write-Output "Signtool: $($signtool.FullName)"

& $signtool.FullName sign /fd SHA256 /f 'D:\goya-on-windows\driver\build\GoyaTest.pfx' /p 'GoyaTest2026' /t http://timestamp.digicert.com 'D:\goya-on-windows\driver\build\goya_bar.sys'
