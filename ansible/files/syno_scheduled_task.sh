#!/bin/sh
# Create or update a Synology DSM 7 UI-visible scheduled task (Control Panel ->
# Task Scheduler). The task runs `cd <workdir> && <script>` daily at hour:minute.
#
# Usage: syno_scheduled_task.sh <id> <name> <hour> <minute> <workdir> <script>
#
# Writes /usr/syno/etc/synoschedule.d/root/<id>.task, then syncs the scheduler
# and restarts crond. Needs no Python; relies on busybox tools only.
set -eu

ID="$1"
NAME="$2"
HOUR="$3"
MINUTE="$4"
WORKDIR="$5"
SCRIPT="$6"

TASK_DIR="/usr/syno/etc/synoschedule.d/root"
SYNC="/usr/syno/bin/synoschedtask"

if [ ! -x "$SYNC" ]; then
    echo "synoschedtask not found at $SYNC; skipping task $NAME" >&2
    exit 1
fi

CMD="cd $WORKDIR && $SCRIPT"

# base64 of the command, without line wrapping
CMD_B64=$(printf '%s' "$CMD" | base64 | tr -d '\n')

# JSON-escape the command for the `script` field (backslash and double quote)
SCRIPT_JSON=$(printf '%s' "$CMD" | sed 's/\\/\\\\/g; s/"/\\"/g')

mkdir -p "$TASK_DIR"

cat > "$TASK_DIR/$ID.task" <<EOF
id=$ID
last work hour=$HOUR
can edit owner=1
can delete from ui=1
edit dialog=SYNO.SDS.TaskScheduler.EditDialog
type=daily
action=#common:run#: $CMD
systemd slice=
monthly week=0
can edit from ui=1
week=1111111
app name=#common:command_line#
name=$NAME
can run app same time=1
owner=0
repeat min store config=[1,5,10,15,20,30]
repeat hour store config=[1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23]
simple edit form=1
repeat hour=0
listable=1
app args={"notify_enable":false,"notify_if_error":false,"notify_mail":"","script":"$SCRIPT_JSON"}
state=enabled
can run task same time=0
start day=0
cmd=$CMD_B64
run hour=$HOUR
edit form=SYNO.SDS.TaskScheduler.Script.FormPanel
app=SYNO.SDS.TaskScheduler.Script
run min=$MINUTE
start month=0
can edit name=1
start year=0
can run from ui=1
repeat min=0
cmdArgv=
EOF

"$SYNC" --sync

if [ -x /usr/syno/bin/synosystemctl ]; then
    /usr/syno/bin/synosystemctl restart crond >/dev/null 2>&1 || true
elif [ -x /usr/syno/sbin/synoservice ]; then
    /usr/syno/sbin/synoservice --restart crond >/dev/null 2>&1 || true
fi

echo "created/updated task id=$ID name=$NAME"
