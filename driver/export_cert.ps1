$cert = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert | Where-Object { $_.Subject -match 'Goya' } | Select-Object -First 1
if ($cert) {
    Export-Certificate -Cert $cert -FilePath 'D:\goya-on-windows\driver\build\GoyaTest.cer' -Type CERT
    Write-Host "Exported: $($cert.Subject) -> GoyaTest.cer"
} else {
    Write-Host "No Goya cert found"
}
