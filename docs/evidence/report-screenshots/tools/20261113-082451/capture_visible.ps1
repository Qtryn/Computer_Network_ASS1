param([long]$WindowId,[string]$OutputPath)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Drawing
Add-Type @'
using System;
using System.Runtime.InteropServices;
public class EvidenceScreen {
 [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left,Top,Right,Bottom; }
 [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
 [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
 [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
 [DllImport("user32.dll")] public static extern IntPtr GetAncestor(IntPtr h,uint flags);
 [DllImport("dwmapi.dll")] public static extern int DwmGetWindowAttribute(IntPtr h,int a,out RECT r,int size);
}
'@
[EvidenceScreen]::SetProcessDPIAware() | Out-Null
if(Test-Path -LiteralPath $OutputPath){throw 'Refusing to overwrite an existing image'}
$captureWindow=[IntPtr]$WindowId
if([EvidenceScreen]::GetAncestor([EvidenceScreen]::GetForegroundWindow(),3) -ne [EvidenceScreen]::GetAncestor($captureWindow,3)) {throw 'Target is not foreground; activate the intended app first'}
$captureRect=New-Object EvidenceScreen+RECT
$captureResult=[EvidenceScreen]::DwmGetWindowAttribute($captureWindow,9,[ref]$captureRect,16)
if($captureResult -ne 0){[EvidenceScreen]::GetWindowRect($captureWindow,[ref]$captureRect) | Out-Null}
$captureWidth=$captureRect.Right-$captureRect.Left
$captureHeight=$captureRect.Bottom-$captureRect.Top
if($captureWidth -lt 50 -or $captureHeight -lt 50){throw 'Invalid window capture bounds'}
$captureBitmap=New-Object System.Drawing.Bitmap($captureWidth,$captureHeight)
$captureGraphics=[System.Drawing.Graphics]::FromImage($captureBitmap)
try {
 $captureGraphics.CopyFromScreen($captureRect.Left,$captureRect.Top,0,0,$captureBitmap.Size,[System.Drawing.CopyPixelOperation]::SourceCopy)
 $captureBitmap.Save($OutputPath,[System.Drawing.Imaging.ImageFormat]::Png)
} finally {$captureGraphics.Dispose();$captureBitmap.Dispose()}
[pscustomobject]@{Path=$OutputPath;Width=$captureWidth;Height=$captureHeight;Left=$captureRect.Left;Top=$captureRect.Top;Method='Actual visible window pixels via CopyFromScreen'} | ConvertTo-Json -Compress
