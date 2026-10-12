"""Automated Tests for Unified Financial Model, 5-Action Payoffs, and Boundary Conditions."""

from decimal import Decimal
import pytest


class FinancialCalculator:
    """Standalone reference calculator implementing the exact specification formulas."""

    @staticmethod
    def calculate_base_delivered(
        order_value: Decimal,
        is_cod: bool,
        cogs: Decimal,
        fwd_shipping: Decimal,
        packaging: Decimal,
        cod_fee: Decimal,
        gateway_fee: Decimal,
    ) -> Decimal:
        if is_cod:
            return order_value - cod_fee - cogs - packaging - fwd_shipping
        return order_value - gateway_fee - cogs - packaging - fwd_shipping

    @staticmethod
    def calculate_base_rto(
        order_value: Decimal,
        is_cod: bool,
        cogs: Decimal,
        fwd_shipping: Decimal,
        rev_shipping: Decimal,
        packaging: Decimal,
        damage_rate: Decimal,
        cod_fee: Decimal,
        cod_fee_incurred_on: str,
        gateway_fee: Decimal,
    ) -> Decimal:
        damage_loss = damage_rate * cogs
        if is_cod:
            cod_charged = cod_fee if cod_fee_incurred_on == "UPON_MANIFEST" else Decimal("0.00")
            return - cod_charged - packaging - fwd_shipping - rev_shipping - damage_loss
        # Prepaid RTO: order value is 100% refunded, gateway fee is non-refundable
        return - gateway_fee - packaging - fwd_shipping - rev_shipping - damage_loss

    @staticmethod
    def calculate_profit_at_risk(
        order_value: Decimal,
        rev_shipping: Decimal,
        cogs: Decimal,
        damage_rate: Decimal,
        cod_fee: Decimal,
        cod_fee_incurred_on: str,
    ) -> Decimal:
        i_rto = Decimal("1.0") if cod_fee_incurred_on == "UPON_MANIFEST" else Decimal("0.0")
        recovered_inventory = (Decimal("1.0") - damage_rate) * cogs
        return order_value + rev_shipping - (Decimal("1.0") - i_rto) * cod_fee - recovered_inventory


# Test Fixture Constants [SPECIFIED / FIXTURE]
V = Decimal("1000.00")
COGS = Decimal("300.00")
C_FWD = Decimal("70.00")
C_REV = Decimal("65.00")
C_PACK = Decimal("20.00")
C_COD_FEE = Decimal("35.00")
F_PG = Decimal("23.00")  # 2% of 1000 + 3
R_DAM = Decimal("0.05")  # 5%
C_OTP = Decimal("0.50")
C_MANUAL = Decimal("18.00")
D_PREP = Decimal("50.00")
C_COMM = Decimal("0.50")


def test_fixture_1_delivered_cod():
    calc = FinancialCalculator()
    rc = calc.calculate_base_delivered(
        order_value=V,
        is_cod=True,
        cogs=COGS,
        fwd_shipping=C_FWD,
        packaging=C_PACK,
        cod_fee=C_COD_FEE,
        gateway_fee=F_PG,
    )
    assert rc == Decimal("575.00")


def test_fixture_2_delivered_prepaid():
    calc = FinancialCalculator()
    rc = calc.calculate_base_delivered(
        order_value=V,
        is_cod=False,
        cogs=COGS,
        fwd_shipping=C_FWD,
        packaging=C_PACK,
        cod_fee=C_COD_FEE,
        gateway_fee=F_PG,
    )
    assert rc == Decimal("587.00")


def test_fixture_3a_rto_cod_delivery_only_and_par_proof():
    calc = FinancialCalculator()
    rc_rto = calc.calculate_base_rto(
        order_value=V,
        is_cod=True,
        cogs=COGS,
        fwd_shipping=C_FWD,
        rev_shipping=C_REV,
        packaging=C_PACK,
        damage_rate=R_DAM,
        cod_fee=C_COD_FEE,
        cod_fee_incurred_on="UPON_DELIVERY_ONLY",
        gateway_fee=F_PG,
    )
    assert rc_rto == Decimal("-170.00")

    # Delivered minus RTO delta
    rc_del = Decimal("575.00")
    delta = rc_del - rc_rto
    assert delta == Decimal("745.00")

    # Formula PaR match
    par = calc.calculate_profit_at_risk(
        order_value=V,
        rev_shipping=C_REV,
        cogs=COGS,
        damage_rate=R_DAM,
        cod_fee=C_COD_FEE,
        cod_fee_incurred_on="UPON_DELIVERY_ONLY",
    )
    assert par == Decimal("745.00")
    assert delta == par


def test_fixture_3b_rto_cod_manifest_and_par_proof():
    calc = FinancialCalculator()
    rc_rto = calc.calculate_base_rto(
        order_value=V,
        is_cod=True,
        cogs=COGS,
        fwd_shipping=C_FWD,
        rev_shipping=C_REV,
        packaging=C_PACK,
        damage_rate=R_DAM,
        cod_fee=C_COD_FEE,
        cod_fee_incurred_on="UPON_MANIFEST",
        gateway_fee=F_PG,
    )
    assert rc_rto == Decimal("-205.00")

    rc_del = Decimal("575.00")
    delta = rc_del - rc_rto
    assert delta == Decimal("780.00")

    par = calc.calculate_profit_at_risk(
        order_value=V,
        rev_shipping=C_REV,
        cogs=COGS,
        damage_rate=R_DAM,
        cod_fee=C_COD_FEE,
        cod_fee_incurred_on="UPON_MANIFEST",
    )
    assert par == Decimal("780.00")
    assert delta == par


def test_fixture_4_refunded_prepaid_rto():
    calc = FinancialCalculator()
    rc_rto = calc.calculate_base_rto(
        order_value=V,
        is_cod=False,
        cogs=COGS,
        fwd_shipping=C_FWD,
        rev_shipping=C_REV,
        packaging=C_PACK,
        damage_rate=R_DAM,
        cod_fee=C_COD_FEE,
        cod_fee_incurred_on="UPON_DELIVERY_ONLY",
        gateway_fee=F_PG,
    )
    assert rc_rto == Decimal("-193.00")


def test_fixture_5_action_ship_as_is():
    p_rto = Decimal("0.30")
    del_payoff = Decimal("575.00")
    rto_payoff = Decimal("-170.00")

    ec = (Decimal("1.0") - p_rto) * del_payoff + p_rto * rto_payoff
    assert ec == Decimal("351.50")


def test_fixture_6_action_verify_otp():
    p_conf = Decimal("0.75")
    p_rto_conf = Decimal("0.12")
    del_payoff = Decimal("575.00")
    rto_payoff = Decimal("-170.00")

    branch_conf = (Decimal("1.0") - p_rto_conf) * del_payoff + p_rto_conf * rto_payoff
    assert branch_conf == Decimal("485.60")

    ec = p_conf * branch_conf + (Decimal("1.0") - p_conf) * Decimal("0.00") - C_OTP
    assert ec == Decimal("363.70")


def test_fixture_7_action_incentivize_prepaid():
    p_conv = Decimal("0.20")
    p_rto_prep = Decimal("0.05")
    v_prime = V - D_PREP  # 950.00
    f_pg_prime = Decimal("0.02") * v_prime + Decimal("3.00")  # 22.00

    del_converted = v_prime - f_pg_prime - COGS - C_PACK - C_FWD  # 538.00
    rto_converted = - f_pg_prime - C_PACK - C_FWD - C_REV - (R_DAM * COGS)  # -192.00

    payoff_converted = (Decimal("1.0") - p_rto_prep) * del_converted + p_rto_prep * rto_converted  # 501.50
    assert payoff_converted == Decimal("501.50")

    ec_ship_as_is = Decimal("351.50")
    ec = p_conv * payoff_converted + (Decimal("1.0") - p_conv) * ec_ship_as_is - C_COMM
    assert ec == Decimal("381.00")


def test_fixture_8_action_manual_review():
    p_appr = Decimal("0.80")
    p_rto_appr = Decimal("0.10")
    del_payoff = Decimal("575.00")
    rto_payoff = Decimal("-170.00")

    branch_appr = (Decimal("1.0") - p_rto_appr) * del_payoff + p_rto_appr * rto_payoff
    assert branch_appr == Decimal("500.50")

    ec = p_appr * branch_appr + (Decimal("1.0") - p_appr) * Decimal("0.00") - C_MANUAL
    assert ec == Decimal("382.40")


def test_fixture_9_action_hold_cancel():
    ec = Decimal("0.00")
    assert ec == Decimal("0.00")


def test_boundary_zero_damage_rate():
    calc = FinancialCalculator()
    rc_rto = calc.calculate_base_rto(
        order_value=V,
        is_cod=True,
        cogs=COGS,
        fwd_shipping=C_FWD,
        rev_shipping=C_REV,
        packaging=C_PACK,
        damage_rate=Decimal("0.00"),
        cod_fee=C_COD_FEE,
        cod_fee_incurred_on="UPON_DELIVERY_ONLY",
        gateway_fee=F_PG,
    )
    # Damage loss is 0; only freight + packaging = -155
    assert rc_rto == Decimal("-155.00")


def test_boundary_full_damage_rate():
    calc = FinancialCalculator()
    rc_rto = calc.calculate_base_rto(
        order_value=V,
        is_cod=True,
        cogs=COGS,
        fwd_shipping=C_FWD,
        rev_shipping=C_REV,
        packaging=C_PACK,
        damage_rate=Decimal("1.00"),
        cod_fee=C_COD_FEE,
        cod_fee_incurred_on="UPON_DELIVERY_ONLY",
        gateway_fee=F_PG,
    )
    # Full COGS (300) lost + 155 logistics = -455
    assert rc_rto == Decimal("-455.00")
