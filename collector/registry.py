"""services/ 폴더의 수집기를 자동 등록한다.

서비스를 추가할 때 파일만 넣으면 되게 하려는 것이다.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil

from .base import ServiceCollector


def discover() -> list[ServiceCollector]:
    """collector.services 아래의 ServiceCollector 구현을 전부 찾아 인스턴스로 준다."""
    from . import services

    found: list[type[ServiceCollector]] = []
    for module_info in pkgutil.iter_modules(services.__path__):
        module = importlib.import_module(f"{services.__name__}.{module_info.name}")
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, ServiceCollector)
                and obj is not ServiceCollector
                and obj.__module__ == module.__name__
            ):
                found.append(obj)

    # 전역 서비스를 먼저 돌려 덤프 순서를 안정시킨다.
    instances = [cls() for cls in found]
    instances.sort(key=lambda c: (not c.is_global, c.dump_name))
    return instances


def all_required_actions() -> list[str]:
    """최소권한 정책의 재료. 쓰기 액션이 섞이면 실패시킨다."""
    actions: set[str] = {"sts:GetCallerIdentity", "iam:ListAccountAliases", "ec2:DescribeRegions"}
    for collector in discover():
        writes = type(collector).write_actions()
        if writes:
            raise AssertionError(
                f"{type(collector).__name__}에 쓰기 액션이 선언됐다: {writes}. "
                "이 도구는 읽기 전용이다."
            )
        actions.update(collector.required_actions)
    return sorted(actions)
