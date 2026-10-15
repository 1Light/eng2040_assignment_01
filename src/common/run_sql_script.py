# Shared - Execute a SQL script file using the Python standard library only

import sqlite3
import sys

DOT_COMMANDS = {
    ".bail",
    ".headers",
    ".mode",
}

SUPPORTED_MODES = {
    "column",
    "list",
}


def is_pending_empty(buffer):
    for line in buffer.splitlines():
        stripped = line.strip()

        if stripped and not stripped.startswith("--"):
            return False

    return True


def split_statements(script):
    statements = []
    buffer = ""

    for line in script.splitlines(keepends=True):
        stripped = line.strip()

        if is_pending_empty(buffer) and stripped.startswith("."):
            command = stripped.split()[0].lower()

            if command not in DOT_COMMANDS:
                raise SystemExit(
                    f"Unsupported sqlite dot-command in script: {stripped}"
                )

            statements.append(("dot", stripped))
            continue

        buffer += line

        if sqlite3.complete_statement(buffer):
            statements.append(("sql", buffer.strip()))
            buffer = ""

    if not is_pending_empty(buffer):
        raise SystemExit(
            "Script ends with an incomplete SQL statement."
        )

    return statements


def render_value(value):
    if value is None:
        return ""

    if isinstance(value, float) and value.is_integer():
        return repr(value)

    return str(value)


def format_column_mode(headers, rows, show_headers):
    widths = [len(name) for name in headers]

    for row in rows:
        for index, value in enumerate(row):
            widths[index] = max(
                widths[index],
                len(render_value(value)),
            )

    lines = []

    if show_headers:
        lines.append(
            "  ".join(
                name.ljust(widths[index])
                for index, name in enumerate(headers)
            ).rstrip()
        )

        lines.append(
            "  ".join("-" * width for width in widths)
        )

    for row in rows:
        lines.append(
            "  ".join(
                render_value(value).ljust(widths[index])
                for index, value in enumerate(row)
            )
        )

    return lines


def format_list_mode(headers, rows, show_headers):
    lines = []

    if show_headers:
        lines.append("|".join(headers))

    for row in rows:
        lines.append(
            "|".join(render_value(value) for value in row)
        )

    return lines


def run(database, script_path):
    with open(script_path, "r", encoding="utf-8") as handle:
        script = handle.read()

    show_headers = False
    mode = "list"

    connection = sqlite3.connect(database, isolation_level=None)

    try:
        for kind, payload in split_statements(script):
            if kind == "dot":
                parts = payload.split()
                command = parts[0].lower()

                if command == ".headers":
                    show_headers = len(parts) > 1 and parts[1].lower() == "on"

                elif command == ".mode":
                    requested = parts[1].lower() if len(parts) > 1 else "list"

                    if requested not in SUPPORTED_MODES:
                        raise SystemExit(
                            f"Unsupported sqlite output mode: {requested}"
                        )

                    mode = requested

                continue

            cursor = connection.execute(payload)

            if cursor.description is None:
                continue

            headers = [column[0] for column in cursor.description]
            rows = cursor.fetchall()

            if mode == "column":
                lines = format_column_mode(headers, rows, show_headers)
            else:
                lines = format_list_mode(headers, rows, show_headers)

            for line in lines:
                print(line)

    finally:
        connection.close()


def main():
    if len(sys.argv) != 3:
        raise SystemExit(
            "Usage: run_sql_script.py <database> <script.sql>"
        )

    run(sys.argv[1], sys.argv[2])


if __name__ == "__main__":
    main()