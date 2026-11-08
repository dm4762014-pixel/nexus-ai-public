param([Parameter(Mandatory=$true)][string]$ArtifactDirectory, [Parameter(Mandatory=$true)][string]$ReviewDirectory, [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9_-]{0,119}$')][string]$BaseName = 'AI-Agents-in-Cybersecurity', [switch]$SkipWord)
$ErrorActionPreference = 'Stop'
$artifacts = (Resolve-Path -LiteralPath $ArtifactDirectory).Path
New-Item -ItemType Directory -Path $ReviewDirectory -Force | Out-Null
$review = (Resolve-Path -LiteralPath $ReviewDirectory).Path
$officeNames = @('POWERPNT','EXCEL')
if (-not $SkipWord) { $officeNames += 'WINWORD' }
if (Get-Process -Name $officeNames -ErrorAction SilentlyContinue) { throw 'An Office application needed for this check is already open; no personal Office instance will be reused.' }
$word = $null; $document = $null
if (-not $SkipWord) {
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false; $word.DisplayAlerts = 0; $word.AutomationSecurity = 3
    $document = $word.Documents.Open((Join-Path $artifacts ($BaseName + '.docx')),$false,$true,$false)
    $document.ExportAsFixedFormat((Join-Path $review 'word.pdf'),17)
} finally {
    if ($document) { $document.Close(0); [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($document) }
    if ($word) { $word.Quit(); [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) }
}
}
$powerpoint = $null; $deck = $null
try {
    $powerpoint = New-Object -ComObject PowerPoint.Application
    $deck = $powerpoint.Presentations.Open((Join-Path $artifacts ($BaseName + '.pptx')),-1,0,0)
    $deck.SaveAs((Join-Path $review 'slides.pdf'),32)
} finally {
    if ($deck) { $deck.Close(); [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($deck) }
    if ($powerpoint) { $powerpoint.Quit(); [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($powerpoint) }
}
$excel = $null; $workbook = $null
try {
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false; $excel.DisplayAlerts = $false; $excel.AskToUpdateLinks = $false; $excel.AutomationSecurity = 3
    $workbook = $excel.Workbooks.Open((Join-Path $artifacts ($BaseName + '.xlsx')),0,$true)
    for ($index=1; $index -le $workbook.Worksheets.Count; $index++) {
        $sheet = $workbook.Worksheets.Item($index)
        $sheet.PageSetup.Orientation = 2; $sheet.PageSetup.Zoom = $false
        $sheet.PageSetup.FitToPagesWide = 1; $sheet.PageSetup.FitToPagesTall = $false
        $sheet.PageSetup.PrintArea = $sheet.UsedRange.Address()
        $sheet.ExportAsFixedFormat(0,(Join-Path $review "sheet-$index.pdf"))
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($sheet)
    }
} finally {
    if ($workbook) { $workbook.Close($false); [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($workbook) }
    if ($excel) { $excel.Quit(); [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel) }
}
Write-Output "Read-only Office exports complete: $review"
