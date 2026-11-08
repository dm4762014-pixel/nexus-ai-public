import json
import zipfile
import pytest
from nexus.coding import generate_project,project_path,validate_sources


@pytest.mark.parametrize("name",["../../host.py","/etc/file.py","C:/file.py","pkg/../file.py","pkg\\file.py","CON.txt",".env","x:stream.py","foo/NUL.txt"])
def test_project_paths_reject_escape_and_reserved_names(tmp_path,name):
    with pytest.raises(ValueError): project_path(tmp_path,name)


def test_static_validation_does_not_execute_generated_code(tmp_path):
    marker=tmp_path/"would-execute.txt"
    code=f"from pathlib import Path\nPath({str(marker)!r}).write_text('unsafe')\n"
    result=validate_sources({"main.py":code})
    assert not marker.exists()
    assert result["checks"][0]["passed"] and not result["build_verified"]
    assert result["imports"]==["pathlib"] and not result["execution_enabled"]


def test_invalid_python_rejected():
    with pytest.raises(SyntaxError): validate_sources({"main.py":"def broken(:"})


def test_compilation_rejects_control_flow_ast_alone_accepts():
    with pytest.raises(SyntaxError): validate_sources({"main.py":"return 1\n"})


def test_unknown_binary_or_too_many_files_rejected():
    with pytest.raises(ValueError): validate_sources({"evil.exe":"code"})
    with pytest.raises(ValueError): validate_sources({f"file{i}.txt":"a" for i in range(13)})


def test_scaffold_archive_is_real_and_honest(tmp_path):
    result=generate_project(tmp_path,"Create a website to organize notes")
    assert result["verified"] and not result["validation"]["execution_enabled"]
    assert result["warnings"] and "not run" in result["content"]
    assert result["incomplete"] and result["content"].startswith("INCOMPLETE")
    with zipfile.ZipFile(tmp_path/result["filename"]) as archive:
        assert archive.testzip() is None
        assert "index.html" in archive.namelist() and "REQUEST.txt" in archive.namelist()
        assert archive.read("REQUEST.txt").decode()=="Create a website to organize notes"


def test_valid_mock_model_project_is_packaged_without_execution(tmp_path):
    class Model:
        def complete(self,system,prompt,tokens=0): return json.dumps({"main.py":"def add(a,b):\n    return a+b\n","test_main.py":"from main import add\ndef test_add():\n    assert add(1,2)==3\n"})
    result=generate_project(tmp_path,"Write an addition function",Model())
    assert "local model" in result["content"] and not result["warnings"]
    assert not result["incomplete"]
    assert not result["validation"]["build_verified"]


def test_malicious_model_path_falls_back_safely(tmp_path):
    class Model:
        def complete(self,system,prompt,tokens=0): return json.dumps({"../outside.py":"print(1)"})
    result=generate_project(tmp_path,"Create an app",Model())
    assert result["warnings"] and "scaffold" in result["content"]
    assert not (tmp_path.parent/"outside.py").exists()


@pytest.mark.parametrize("value",[
    {"main.py":123},
    {"files":{"main.py":"pass"}},
    {f"file{i}.py":"pass" for i in range(5)},
    {"main.py":"#"*4001},
    {"main.py":""},
    {"README.md":"packager metadata override"},
])
def test_invalid_model_schema_falls_back_with_incomplete_flag(tmp_path,value):
    class Model:
        def complete(self,system,prompt,tokens=0):
            assert tokens==650
            return json.dumps(value)
    result=generate_project(tmp_path,"Write an addition function",Model())
    assert result["incomplete"] and result["warnings"]


def test_duplicate_model_filenames_are_rejected(tmp_path):
    class Model:
        def complete(self,system,prompt,tokens=0): return '{"main.py":"pass","main.py":"print(1)"}'
    result=generate_project(tmp_path,"Write an addition function",Model())
    assert result["incomplete"]


def test_missing_local_test_import_is_repaired_without_execution(tmp_path):
    class Model:
        def complete(self,system,prompt,tokens=0):
            return json.dumps({"main.py":"def add(a,b):\n    return a+b\n","test_main.py":"import unittest\nclass TestAdd(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(add(2,3),5)\n"})
    result=generate_project(tmp_path,"Write addition and its tests",Model())
    assert not result["incomplete"] and not result["validation"]["unresolved_globals"]
    with zipfile.ZipFile(tmp_path/result["filename"]) as archive:
        assert archive.read("test_main.py").decode().startswith("from main import add\n")


def test_unresolved_python_names_remain_visible():
    result=validate_sources({"main.py":"def main():\n    return missing_name\n"})
    assert result["unresolved_globals"]=={"main.py":["missing_name"]}
    assert not next(c for c in result["checks"] if c["check"]=="Static global references")["passed"]


def test_future_import_precedes_repaired_test_import(tmp_path):
    class Model:
        def complete(self,system,prompt,tokens=0):
            return json.dumps({"main.py":"def add(a,b):\n    return a+b\n","test_main.py":'"""Tests."""\nfrom __future__ import annotations\ndef test_add():\n    assert add(2,3)==5\n'})
    result=generate_project(tmp_path,"Write addition and its tests",Model())
    assert not result["incomplete"]
    with zipfile.ZipFile(tmp_path/result["filename"]) as archive:
        source=archive.read("test_main.py").decode()
        assert source.index("from __future__")<source.index("from main import add")
