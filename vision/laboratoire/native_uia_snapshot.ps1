param(
    [Parameter(Mandatory=$true)][long]$WindowHandle,
    [Parameter(Mandatory=$true)][int]$ExpectedProcessId,
    [switch]$HitTest,
    [int]$PointX,
    [int]$PointY,
    [switch]$Worker
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName WindowsBase
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class AliceObservationWindow {
    [DllImport("user32.dll")] public static extern bool IsWindow(IntPtr hwnd);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint pid);
    [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(POINT point);
    [DllImport("user32.dll")] public static extern IntPtr GetAncestor(IntPtr hwnd, uint flags);
    [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X; public int Y; }
}
'@
$handle = [IntPtr]$WindowHandle
function Check-Window {
    [uint32]$owner = 0
    if (-not [AliceObservationWindow]::IsWindow($handle)) { throw 'native_window_unavailable' }
    $null = [AliceObservationWindow]::GetWindowThreadProcessId($handle, [ref]$owner)
    if ($owner -ne $ExpectedProcessId) { throw 'native_window_owner_changed' }
    if ([AliceObservationWindow]::GetForegroundWindow() -ne $handle) { throw 'native_focus_lost' }
    return @{ hwnd=$WindowHandle; pid=[int]$owner; available=$true; foreground=$true }
}
function Read-Rect($rect) {
    # WPF legitimately exposes Rect.Empty for off-screen structural nodes.
    # Keep them non-actionable rather than failing the entire observation.
    if ($rect.IsEmpty) { return ,@(0,0,0,0) }
    $values = @($rect.X, $rect.Y, $rect.Width, $rect.Height)
    foreach ($number in $values) {
        if ([double]::IsNaN($number) -or [double]::IsInfinity($number)) { throw 'invalid_native_geometry' }
    }
    if ($rect.Width -lt 0 -or $rect.Height -lt 0) { throw 'invalid_native_geometry' }
    return ,$values
}
function Get-NativeSnapshot {
param([switch]$HitTest, [int]$PointX, [int]$PointY)
$before = Check-Window
$root = [System.Windows.Automation.AutomationElement]::FromHandle($handle)
if ($null -eq $root -or $root.Current.ProcessId -ne $ExpectedProcessId) { throw 'native_uia_root_invalid' }
$walker = [System.Windows.Automation.TreeWalker]::RawViewWalker
if ($HitTest) {
    $nativePoint = New-Object AliceObservationWindow+POINT
    $nativePoint.X = $PointX
    $nativePoint.Y = $PointY
    $pointWindow = [AliceObservationWindow]::WindowFromPoint($nativePoint)
    if ([AliceObservationWindow]::GetAncestor($pointWindow, 2) -ne $handle) { throw 'native_point_occluded' }
    $point = New-Object System.Windows.Point($PointX, $PointY)
    $hit = [System.Windows.Automation.AutomationElement]::FromPoint($point)
    $ancestor = $hit
    $belongs = $false
    for ($depth=0; $depth -le 64 -and $null -ne $ancestor; $depth++) {
        if ([System.Windows.Automation.Automation]::Compare($ancestor, $root)) { $belongs=$true; break }
        $ancestor = $walker.GetParent($ancestor)
    }
    if (-not $belongs -or $hit.Current.ProcessId -ne $ExpectedProcessId) { throw 'native_hit_outside_window' }
    $result = @{ checks_before=$before; hit_id=($hit.GetRuntimeId() -join '.'); checks_after=(Check-Window) }
} else {
    $items = New-Object 'System.Collections.Generic.List[object]'
    $queue = New-Object 'System.Collections.Generic.Queue[object]'
    $queue.Enqueue(@{ element=$root; depth=0; parent_id=$null })
    $truncated = $false
    while ($queue.Count -gt 0) {
        if ($items.Count -ge 200) { $truncated=$true; break }
        $entry = $queue.Dequeue()
        $element = $entry.element
        $current = $element.Current
        if ($current.ProcessId -ne $ExpectedProcessId) { throw 'native_element_owner_changed' }
        $password = $current.IsPassword
        $name = ''
        $value = $null
        $editable = $false
        $selected = $null
        $selectionPattern = $null
        if ($element.TryGetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern, [ref]$selectionPattern)) {
            $selected = $selectionPattern.Current.IsSelected
        }
        if (-not $password) {
            $name = $current.Name
            if ($name.Length -gt 4000) { $name=$name.Substring(0,4000); $truncated=$true }
            $pattern = $null
            if ($element.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$pattern)) {
                $value = $pattern.Current.Value
                $editable = -not $pattern.Current.IsReadOnly
            } elseif ($element.TryGetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern, [ref]$pattern)) {
                $value = $pattern.DocumentRange.GetText(4001)
            }
            if ($null -ne $value -and $value.Length -gt 4000) { $value=$value.Substring(0,4000); $truncated=$true }
        }
        $elementId = ($element.GetRuntimeId() -join '.')
        $items.Add(@{
            id=$elementId; parent_id=$entry.parent_id; name=$name; type=$current.ControlType.ProgrammaticName;
            rect=(Read-Rect $current.BoundingRectangle); enabled=$current.IsEnabled; editable=$editable; selected=$selected;
            visible=((-not $current.IsOffscreen) -and (-not $current.BoundingRectangle.IsEmpty)); focused=$current.HasKeyboardFocus; value=$value; password=$password
        })
        # Never inspect descendants of a password element.
        if ($password) { continue }
        $child = $walker.GetFirstChild($element)
        # Modern tabbed editors have decorative children below level six.
        # Keep a bounded depth without rejecting their otherwise small tree.
        if ($entry.depth -ge 12) {
            if ($null -ne $child) { $truncated=$true }
            continue
        }
        while ($null -ne $child) {
            if (($items.Count + $queue.Count) -ge 200) { $truncated=$true; break }
            $queue.Enqueue(@{ element=$child; depth=($entry.depth + 1); parent_id=$elementId })
            $child = $walker.GetNextSibling($child)
        }
    }
    $geometry = Read-Rect $root.Current.BoundingRectangle
    $result = @{ checks_before=$before; checks_after=(Check-Window); geometry=$geometry;
        elements=@($items.ToArray()); truncated=$truncated }
}
return $result
}

if (-not $Worker) {
    Get-NativeSnapshot -HitTest:$HitTest -PointX $PointX -PointY $PointY | ConvertTo-Json -Depth 12 -Compress
    return
}

# The launch arguments bind this process to one window. Requests cannot rebind it.
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
$safeErrors = @(
    'native_window_unavailable', 'native_window_owner_changed', 'native_focus_lost',
    'invalid_native_geometry', 'native_uia_root_invalid', 'native_point_occluded',
    'native_hit_outside_window', 'native_element_owner_changed',
    'native_request_invalid', 'native_request_too_large'
)
while ($null -ne ($line = [Console]::ReadLine())) {
    $requestId = $null
    try {
        if ($line.Length -gt 1024 -or [Text.Encoding]::UTF8.GetByteCount($line) -gt 1024) {
            throw 'native_request_too_large'
        }
        $request = ConvertFrom-Json -InputObject $line
        if ($null -eq $request -or $request -isnot [System.Management.Automation.PSCustomObject]) {
            throw 'native_request_invalid'
        }
        if ($request.id -isnot [int] -and $request.id -isnot [long]) { throw 'native_request_invalid' }
        if ($request.id -lt [int]::MinValue -or $request.id -gt [int]::MaxValue) { throw 'native_request_invalid' }
        $requestId = [int]$request.id
        foreach ($property in $request.PSObject.Properties.Name) {
            if ($property -cnotin @('id', 'op', 'x', 'y')) { throw 'native_request_invalid' }
        }
        if ($request.op -isnot [string] -or $request.op -cnotin @('read', 'hit_test')) {
            throw 'native_request_invalid'
        }
        foreach ($coordinate in @('x', 'y')) {
            if ($request.op -ceq 'hit_test' -or $coordinate -cin $request.PSObject.Properties.Name) {
                $number = $request.$coordinate
                if ($number -isnot [int] -and $number -isnot [long]) { throw 'native_request_invalid' }
                if ($number -lt [int]::MinValue -or $number -gt [int]::MaxValue) { throw 'native_request_invalid' }
            }
        }
        if ($request.op -ceq 'hit_test') {
            $data = Get-NativeSnapshot -HitTest -PointX $request.x -PointY $request.y
        } else {
            $data = Get-NativeSnapshot
        }
        $response = @{ id=$requestId; ok=$true; data=$data }
    } catch {
        $code = 'native_uia_failed'
        if ($_.Exception.Message -cin $safeErrors) { $code=$_.Exception.Message }
        $response = @{ id=$requestId; ok=$false; error=$code }
    }
    $json = $response | ConvertTo-Json -Depth 14 -Compress
    if (([Text.Encoding]::UTF8.GetByteCount($json) + 2) -gt 2MB) {
        $json = @{ id=$requestId; ok=$false; error='native_response_too_large' } | ConvertTo-Json -Compress
    }
    [Console]::WriteLine($json)
    [Console]::Out.Flush()
    # Do not retain the previous observation while idle on the input pipe.
    $data = $null
    $response = $null
    $json = $null
    $request = $null
    $line = $null
}
