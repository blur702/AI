# Update Congressional Scraper to run at midnight
$taskName = "CongressionalScraperStart9PM"

# Get the task
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue

if ($task) {
    # Create new trigger for midnight
    $trigger = New-ScheduledTaskTrigger -Daily -At "12:00AM"

    # Update the task
    Set-ScheduledTask -TaskName $taskName -Trigger $trigger

    # Rename to reflect new time
    # Note: Can't rename, so we'll just note this in the output
    Write-Host "Task '$taskName' updated to run at midnight (12:00 AM)"
    Write-Host "Consider renaming the task to 'CongressionalScraperMidnight'"

    # Show new schedule
    Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo
} else {
    Write-Host "Task not found: $taskName"
}
