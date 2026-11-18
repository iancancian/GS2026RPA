"""Exceções de domínio. Cada uma mapeia para um código de saída do robô."""


class BocaDeLoboError(Exception):
    exit_code = 1


class ConfigError(BocaDeLoboError):
    exit_code = 4


class ForecastUnavailable(BocaDeLoboError):
    """Previsão indisponível (API fora do ar e sem cache válido)."""

    exit_code = 2


class InputDataError(BocaDeLoboError):
    """Arquivo de entrada ausente ou com estrutura inválida."""

    exit_code = 3
