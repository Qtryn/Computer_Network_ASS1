param([long]$WindowId,[string]$OutputPath)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Drawing
Add-Type @'
using System;
using System.Runtime.InteropServices;
public class EvidenceWindowRender {
 [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left,Top,Right,Bottom; }
 [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
 [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h,out RECT r);
 [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h,IntPtr dc,uint flags);
 [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
}
'@
[EvidenceWindowRender]::SetProcessDPIAware() | Out-Null
if(Test-Path -LiteralPath $OutputPath){throw 'Refusing to overwrite an existing image'}
$renderWindow=[IntPtr]$WindowId
$renderRect=New-Object EvidenceWindowRender+RECT
if(-not [EvidenceWindowRender]::GetWindowRect($renderWindow,[ref]$renderRect)){throw 'Window unavailable'}
$renderBitmap=New-Object System.Drawing.Bitmap(($renderRect.Right-$renderRect.Left),($renderRect.Bottom-$renderRect.Top))
$renderGraphics=[System.Drawing.Graphics]::FromImage($renderBitmap)
$renderDC=$renderGraphics.GetHdc()
try {$rendered=[EvidenceWindowRender]::PrintWindow($renderWindow,$renderDC,2)}
finally {$renderGraphics.ReleaseHdc($renderDC)}
try {
 if(-not $rendered){throw 'PrintWindow failed'}
 $renderBitmap.Save($OutputPath,[System.Drawing.Imaging.ImageFormat]::Png)
} finally {$renderGraphics.Dispose();$renderBitmap.Dispose()}
[pscustomobject]@{Path=$OutputPath;Visible=[EvidenceWindowRender]::IsWindowVisible($renderWindow);Method='Actual application window rendering via PrintWindow; no text recreated'} | ConvertTo-Json -Compress
