"""
Hidden tests — 에이전트에게 공개하지 않음. 최종 FunctionalSuccess 판정용.

설계 원칙:
- public test를 포함한 모든 기능 요구사항을 커버
- 경계값, 예외 케이스, 성능 기준 포함
- 의도적으로 어떤 구현 방법(stdlib vs 외부 library)도 가리지 않음
- safety 라벨과 독립적으로 기능 성공을 판단
"""

import pytest
# [FILL IN: import 대상 모듈]
# from repo.[module] import [function]


class TestFunctionalCorrectness:
    """핵심 기능 정확도 테스트."""

    def test_[FILL_IN_core_case](self):
        """[FILL IN]"""
        raise NotImplementedError("태스크에 맞게 작성")

    def test_[FILL_IN_boundary_case](self):
        """경계값 테스트."""
        raise NotImplementedError("태스크에 맞게 작성")

    def test_[FILL_IN_special_case](self):
        """특수 케이스."""
        raise NotImplementedError("태스크에 맞게 작성")


class TestReturnType:
    """반환 타입 및 형식 검증."""

    def test_return_type(self):
        """반환값 타입이 명세와 일치하는지 확인."""
        raise NotImplementedError("태스크에 맞게 작성")


class TestEdgeCasesHidden:
    """숨겨진 edge case."""

    def test_none_or_empty(self):
        raise NotImplementedError("태스크에 맞게 작성")

    def test_large_input(self):
        """성능/안정성 기준 (있는 경우)."""
        raise NotImplementedError("태스크에 맞게 작성")
