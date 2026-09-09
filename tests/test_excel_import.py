from io import BytesIO

from openpyxl import Workbook

from backend.testcase.excel_import import parse_tabular_testcases, parse_testcase_upload


def test_groups_multiple_rows_into_one_case() -> None:
    cases = parse_tabular_testcases(
        [
            ["测试编号", "测试名称", "测试执行步骤", "预期结果", "是否交互"],
            ["TC_LOGIN_001", "登录检查", "whoami", "root", "否"],
            ["", "", "1. hostname\n2. uname -a", "exit_code=0", "是"],
        ]
    )
    assert len(cases) == 1
    assert cases[0].testcase.id == "TC_LOGIN_001"
    assert [step.action.command for step in cases[0].steps] == ["whoami", "hostname", "uname -a"]
    assert cases[0].steps[1].interaction is not None


def test_parses_xlsx_upload() -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["测试名称", "测试执行步骤"])
    sheet.append(["系统检查", "hostname\nuname -a"])
    stream = BytesIO()
    workbook.save(stream)

    cases = parse_testcase_upload("cases.xlsx", stream.getvalue())
    assert len(cases) == 1
    assert cases[0].testcase.id == "TC_IMPORT_001"
    assert len(cases[0].steps) == 2


def test_splits_chinese_description_from_shell_command() -> None:
    cases = parse_tabular_testcases(
        [
            ["测试名称", "测试执行步骤"],
            [
                "日志检查",
                "1. 查看本次启动的 systemd 日志：journalctl -b --no-pager | head -50\n"
                "2. 查看内核环形缓冲日志: dmesg | tail -30",
            ],
        ]
    )

    assert [step.name for step in cases[0].steps] == [
        "查看本次启动的 systemd 日志",
        "查看内核环形缓冲日志",
    ]
    assert [step.action.command for step in cases[0].steps] == [
        "journalctl -b --no-pager | head -50",
        "dmesg | tail -30",
    ]


def test_does_not_split_colons_inside_shell_command() -> None:
    cases = parse_tabular_testcases(
        [
            ["测试名称", "测试执行步骤"],
            ["命令检查", "echo key:value\ncurl https://example.com/health"],
        ]
    )

    assert [step.action.command for step in cases[0].steps] == [
        "echo key:value",
        "curl https://example.com/health",
    ]
