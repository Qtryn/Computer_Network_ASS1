param([string]$RecipePath,[string]$OutputPath)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Drawing
if(Test-Path -LiteralPath $OutputPath){throw 'Refusing to overwrite existing evidence'}
$recipe=Get-Content -LiteralPath $RecipePath -Raw | ConvertFrom-Json
$bitmap=New-Object System.Drawing.Bitmap([int]$recipe.width,[int]$recipe.height)
$graphics=[System.Drawing.Graphics]::FromImage($bitmap)
$font=New-Object System.Drawing.Font('Segoe UI',14,[System.Drawing.FontStyle]::Bold)
try {
 $graphics.Clear([System.Drawing.Color]::White)
 foreach($panel in $recipe.panels){
  if($panel.label){$graphics.DrawString([string]$panel.label,$font,[System.Drawing.Brushes]::Black,[single]$panel.dx,[single]($panel.dy-28))}
  $source=[System.Drawing.Image]::FromFile([string]$panel.source)
  try {
   $crop=New-Object System.Drawing.Rectangle([int]$panel.x,[int]$panel.y,[int]$panel.w,[int]$panel.h)
   $target=New-Object System.Drawing.Rectangle([int]$panel.dx,[int]$panel.dy,[int]$panel.w,[int]$panel.h)
   $graphics.DrawImage($source,$target,$crop,[System.Drawing.GraphicsUnit]::Pixel)
  } finally {$source.Dispose()}
 }
 $bitmap.Save($OutputPath,[System.Drawing.Imaging.ImageFormat]::Png)
} finally {$font.Dispose();$graphics.Dispose();$bitmap.Dispose()}
Get-Item -LiteralPath $OutputPath | Select-Object FullName,Length
