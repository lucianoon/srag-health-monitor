"""
Sistema de Guardrails para validação e segurança.

Este módulo implementa validações em múltiplas camadas para garantir
a qualidade e segurança dos dados e operações.
"""

from typing import Dict, Any, List, Tuple
import re
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class InputValidator:
    """Validador de entradas do sistema."""
    
    @staticmethod
    def validate_query_type(query_type: str) -> Tuple[bool, str]:
        """
        Valida tipo de consulta ao banco de dados.
        
        Args:
            query_type: Tipo de consulta
            
        Returns:
            Tupla (válido, mensagem)
        """
        valid_types = ['metrics', 'daily_cases', 'monthly_cases']
        
        if query_type not in valid_types:
            return False, f"Tipo de consulta inválido. Tipos válidos: {valid_types}"
        
        return True, "OK"
    
    @staticmethod
    def validate_days_parameter(days: int) -> Tuple[bool, str]:
        """
        Valida parâmetro de dias.
        
        Args:
            days: Número de dias
            
        Returns:
            Tupla (válido, mensagem)
        """
        if not isinstance(days, int):
            return False, "Parâmetro 'days' deve ser um inteiro"
        
        if days < 1:
            return False, "Parâmetro 'days' deve ser maior que 0"
        
        if days > 365:
            return False, "Parâmetro 'days' não pode exceder 365"
        
        return True, "OK"
    
    @staticmethod
    def validate_months_parameter(months: int) -> Tuple[bool, str]:
        """
        Valida parâmetro de meses.
        
        Args:
            months: Número de meses
            
        Returns:
            Tupla (válido, mensagem)
        """
        if not isinstance(months, int):
            return False, "Parâmetro 'months' deve ser um inteiro"
        
        if months < 1:
            return False, "Parâmetro 'months' deve ser maior que 0"
        
        if months > 24:
            return False, "Parâmetro 'months' não pode exceder 24"
        
        return True, "OK"
    
    @staticmethod
    def sanitize_search_query(query: str) -> str:
        """
        Sanitiza query de busca removendo caracteres perigosos.
        
        Args:
            query: Query de busca
            
        Returns:
            Query sanitizada
        """
        # Remover caracteres especiais perigosos
        sanitized = re.sub(r"[<>\"'%;()&+]", '', query)
        
        # Limitar tamanho
        sanitized = sanitized[:200]
        
        logger.info(f"Query sanitizada: {sanitized}")
        return sanitized


class OutputValidator:
    """Validador de saídas do sistema."""
    
    @staticmethod
    def validate_metrics(metrics: Dict[str, float]) -> Tuple[bool, str]:
        """
        Valida métricas calculadas.
        
        Args:
            metrics: Dicionário de métricas
            
        Returns:
            Tupla (válido, mensagem)
        """
        required_keys = ['taxa_aumento_casos', 'taxa_mortalidade', 
                        'taxa_ocupacao_uti', 'taxa_vacinacao']
        
        # Verificar chaves obrigatórias
        for key in required_keys:
            if key not in metrics:
                return False, f"Métrica obrigatória ausente: {key}"
        
        # Validar ranges
        if not (-100 <= metrics['taxa_aumento_casos'] <= 1000):
            return False, "Taxa de aumento de casos fora do range esperado"
        
        if not (0 <= metrics['taxa_mortalidade'] <= 100):
            return False, "Taxa de mortalidade fora do range esperado (0-100%)"
        
        if not (0 <= metrics['taxa_ocupacao_uti'] <= 100):
            return False, "Taxa de ocupação de UTI fora do range esperado (0-100%)"
        
        if not (0 <= metrics['taxa_vacinacao'] <= 100):
            return False, "Taxa de vacinação fora do range esperado (0-100%)"
        
        return True, "OK"
    
    @staticmethod
    def validate_report_content(report: str) -> Tuple[bool, str]:
        """
        Valida conteúdo do relatório gerado.
        
        Args:
            report: Conteúdo do relatório
            
        Returns:
            Tupla (válido, mensagem)
        """
        if not report or len(report) < 100:
            return False, "Relatório muito curto ou vazio"
        
        # Verificar seções obrigatórias
        required_sections = ['Métricas Principais', 'Taxa de Mortalidade', 
                            'Taxa de Ocupação de UTI', 'Taxa de Vacinação']
        
        for section in required_sections:
            if section not in report:
                return False, f"Seção obrigatória ausente: {section}"
        
        return True, "OK"


class DataPrivacyGuard:
    """Guardrail para proteção de dados sensíveis (LGPD)."""
    
    # Padrões de dados sensíveis
    CPF_PATTERN = r'\d{3}\.\d{3}\.\d{3}-\d{2}'
    RG_PATTERN = r'\d{1,2}\.\d{3}\.\d{3}-\d{1,2}'
    PHONE_PATTERN = r'\(\d{2}\)\s?\d{4,5}-?\d{4}'
    EMAIL_PATTERN = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    
    @staticmethod
    def check_for_pii(text: str) -> Tuple[bool, List[str]]:
        """
        Verifica presença de informações pessoais identificáveis (PII).
        
        Args:
            text: Texto a verificar
            
        Returns:
            Tupla (contém_pii, lista_de_tipos_encontrados)
        """
        pii_found = []
        
        if re.search(DataPrivacyGuard.CPF_PATTERN, text):
            pii_found.append('CPF')
        
        if re.search(DataPrivacyGuard.RG_PATTERN, text):
            pii_found.append('RG')
        
        if re.search(DataPrivacyGuard.PHONE_PATTERN, text):
            pii_found.append('Telefone')
        
        if re.search(DataPrivacyGuard.EMAIL_PATTERN, text):
            pii_found.append('Email')
        
        has_pii = len(pii_found) > 0
        
        if has_pii:
            logger.warning(f"PII detectado no texto: {pii_found}")
        
        return has_pii, pii_found
    
    @staticmethod
    def anonymize_text(text: str) -> str:
        """
        Anonimiza informações pessoais no texto.
        
        Args:
            text: Texto a anonimizar
            
        Returns:
            Texto anonimizado
        """
        # Anonimizar CPF
        text = re.sub(DataPrivacyGuard.CPF_PATTERN, '***.***.***-**', text)
        
        # Anonimizar RG
        text = re.sub(DataPrivacyGuard.RG_PATTERN, '**.***.***-*', text)
        
        # Anonimizar telefone
        text = re.sub(DataPrivacyGuard.PHONE_PATTERN, '(**) ****-****', text)
        
        # Anonimizar email
        text = re.sub(DataPrivacyGuard.EMAIL_PATTERN, '***@***.***', text)
        
        logger.info("Texto anonimizado com sucesso")
        return text


class RateLimiter:
    """Limitador de taxa de chamadas."""
    
    def __init__(self, max_calls_per_minute: int = 60):
        """
        Inicializa o rate limiter.
        
        Args:
            max_calls_per_minute: Máximo de chamadas por minuto
        """
        self.max_calls = max_calls_per_minute
        self.calls = []
    
    def check_rate_limit(self) -> Tuple[bool, str]:
        """
        Verifica se a taxa de chamadas está dentro do limite.
        
        Returns:
            Tupla (permitido, mensagem)
        """
        now = datetime.now()
        
        # Remover chamadas antigas (mais de 1 minuto)
        self.calls = [call_time for call_time in self.calls 
                     if (now - call_time).total_seconds() < 60]
        
        if len(self.calls) >= self.max_calls:
            return False, f"Taxa de chamadas excedida ({self.max_calls}/min)"
        
        self.calls.append(now)
        return True, "OK"


# Instância global do rate limiter
rate_limiter = RateLimiter(max_calls_per_minute=60)


if __name__ == "__main__":
    # Testes dos guardrails
    print("\n=== Teste: Validação de Entrada ===")
    valid, msg = InputValidator.validate_query_type("metrics")
    print(f"Query type 'metrics': {valid} - {msg}")
    
    valid, msg = InputValidator.validate_days_parameter(30)
    print(f"Days parameter 30: {valid} - {msg}")
    
    valid, msg = InputValidator.validate_days_parameter(500)
    print(f"Days parameter 500: {valid} - {msg}")
    
    print("\n=== Teste: Validação de Saída ===")
    metrics = {
        'taxa_aumento_casos': -3.67,
        'taxa_mortalidade': 7.67,
        'taxa_ocupacao_uti': 27.89,
        'taxa_vacinacao': 52.90
    }
    valid, msg = OutputValidator.validate_metrics(metrics)
    print(f"Métricas válidas: {valid} - {msg}")
    
    print("\n=== Teste: Proteção de Dados (LGPD) ===")
    text_with_pii = "Paciente João Silva, CPF 123.456.789-00, telefone (11) 98765-4321"
    has_pii, types = DataPrivacyGuard.check_for_pii(text_with_pii)
    print(f"Contém PII: {has_pii} - Tipos: {types}")
    
    anonymized = DataPrivacyGuard.anonymize_text(text_with_pii)
    print(f"Texto anonimizado: {anonymized}")
    
    print("\n=== Teste: Rate Limiter ===")
    for i in range(3):
        allowed, msg = rate_limiter.check_rate_limit()
        print(f"Chamada {i+1}: {allowed} - {msg}")
