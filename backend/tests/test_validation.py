"""Tests for Pydantic validation schemas."""

import pytest
from pydantic import ValidationError

from services.validation import (
    RegisterBody,
    LoginBody,
    RefreshBody,
    SimulatorExecuteBody,
    SimulatorCloseBody,
    SimulatorResetBody,
    AnalyzeStockBody,
    ChatSendBody,
    ChangePasswordBody,
    ForgotPasswordBody,
    ResetPasswordBody,
)


class TestRegisterBody:
    def test_valid(self):
        b = RegisterBody(email="User@Example.COM", password="StrongPass1!", name="  Alice  ")
        assert b.email == "user@example.com"
        assert b.name == "Alice"

    def test_email_no_at(self):
        with pytest.raises(ValidationError):
            RegisterBody(email="nodomain", password="StrongPass1!", name="X")

    def test_short_password(self):
        with pytest.raises(ValidationError):
            RegisterBody(email="a@b.com", password="short", name="X")

    def test_empty_name(self):
        with pytest.raises(ValidationError):
            RegisterBody(email="a@b.com", password="StrongPass1!", name="")


class TestSimulatorExecuteBody:
    def test_valid(self):
        b = SimulatorExecuteBody(symbol="tcs", quantity=10, atr=5.5)
        assert b.symbol == "TCS"
        assert b.trail_multiplier == 1.5

    def test_zero_quantity(self):
        with pytest.raises(ValidationError):
            SimulatorExecuteBody(symbol="TCS", quantity=0, atr=5.5)

    def test_negative_atr(self):
        with pytest.raises(ValidationError):
            SimulatorExecuteBody(symbol="TCS", quantity=10, atr=-1.0)

    def test_trail_multiplier_out_of_range(self):
        with pytest.raises(ValidationError):
            SimulatorExecuteBody(symbol="TCS", quantity=10, atr=5.0, trail_multiplier=10.0)


class TestSimulatorResetBody:
    def test_defaults(self):
        b = SimulatorResetBody()
        assert b.initial_capital == 1_000_000

    def test_too_low(self):
        with pytest.raises(ValidationError):
            SimulatorResetBody(initial_capital=100)


class TestAnalyzeStockBody:
    def test_symbol_uppercased(self):
        b = AnalyzeStockBody(symbol="infy")
        assert b.symbol == "INFY"

    def test_invalid_provider(self):
        with pytest.raises(ValidationError):
            AnalyzeStockBody(symbol="INFY", llm_provider="gpt7")


class TestChatSendBody:
    def test_empty_message(self):
        with pytest.raises(ValidationError):
            ChatSendBody(message="")

    def test_too_long_message(self):
        with pytest.raises(ValidationError):
            ChatSendBody(message="x" * 5000)


class TestChangePasswordBody:
    def test_valid(self):
        b = ChangePasswordBody(current_password="old", new_password="NewSecure1!")
        assert b.new_password == "NewSecure1!"

    def test_short_new_password(self):
        with pytest.raises(ValidationError):
            ChangePasswordBody(current_password="old", new_password="short")

    def test_empty_current(self):
        with pytest.raises(ValidationError):
            ChangePasswordBody(current_password="", new_password="NewSecure1!")


class TestForgotPasswordBody:
    def test_valid(self):
        b = ForgotPasswordBody(email="Test@Example.COM")
        assert b.email == "test@example.com"

    def test_empty_email(self):
        with pytest.raises(ValidationError):
            ForgotPasswordBody(email="")


class TestResetPasswordBody:
    def test_valid(self):
        b = ResetPasswordBody(token="a" * 20, new_password="NewSecure1!")
        assert b.new_password == "NewSecure1!"

    def test_short_token(self):
        with pytest.raises(ValidationError):
            ResetPasswordBody(token="short", new_password="NewSecure1!")

    def test_short_password(self):
        with pytest.raises(ValidationError):
            ResetPasswordBody(token="a" * 20, new_password="short")
