param([Parameter(Mandatory=$true)][string]$ImagePath)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]
$asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
} | Select-Object -First 1
function Await-WinRT($Operation, [Type]$ResultType) {
    $task = $asTask.MakeGenericMethod($ResultType).Invoke($null, @($Operation))
    $task.GetAwaiter().GetResult()
}
$file = Await-WinRT ([Windows.Storage.StorageFile]::GetFileFromPathAsync($ImagePath)) ([Windows.Storage.StorageFile])
$stream = Await-WinRT ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
try {
    $decoder = Await-WinRT ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $bitmap = Await-WinRT ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
    try {
        $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
        if ($null -eq $engine) { throw 'Nenhum idioma de OCR instalado no Windows.' }
        $result = Await-WinRT ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
        # Recover column gaps instead of collapsing tables into one text run.
        $words = @($result.Lines | ForEach-Object { $_.Words } | Sort-Object { $_.BoundingRect.Y })
        $rows = [System.Collections.Generic.List[object]]::new()
        foreach ($word in $words) {
            $rect = $word.BoundingRect
            $center = $rect.Y + $rect.Height / 2
            $row = $rows | Where-Object { [Math]::Abs($_.Center - $center) -lt ([Math]::Max(4,$rect.Height * 0.55)) } | Select-Object -Last 1
            if ($null -eq $row) {
                $row = [PSCustomObject]@{ Center=$center; Words=[System.Collections.Generic.List[object]]::new() }
                $rows.Add($row)
            }
            $row.Words.Add($word)
        }
        foreach ($line in ($rows | Sort-Object Center)) {
            $text = ''
            $lastRight = 0
            foreach ($word in ($line.Words | Sort-Object { $_.BoundingRect.X })) {
                $rect = $word.BoundingRect
                $charWidth = [Math]::Max(1, $rect.Width / [Math]::Max(1, $word.Text.Length))
                $gap = if ($text.Length -eq 0) { 0 } else { [Math]::Max(1, [int](($rect.X - $lastRight) / $charWidth)) }
                $text += (' ' * [Math]::Min(100,$gap)) + $word.Text
                $lastRight = $rect.X + $rect.Width
            }
            [Console]::WriteLine($text)
        }
    } finally { if ($bitmap) { $bitmap.Dispose() } }
} finally { if ($stream) { $stream.Dispose() } }
