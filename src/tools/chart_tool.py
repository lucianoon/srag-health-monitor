"""Ferramenta responsável por gerar gráficos (SVG) para o relatório de SRAG."""

from dataclasses import dataclass
from typing import Dict, Any, List, Sequence
from datetime import datetime
from pathlib import Path
import json
import logging

from utils.paths import REPORTS_DIR, ensure_directory, resolve_path
from .base import ToolBase

logger = logging.getLogger(__name__)


@dataclass
class ChartGenerationInput:
    """Estrutura de entrada para documentação e compatibilidade."""

    chart_type: str
    data: str
    output_path: str = str(REPORTS_DIR)


class ChartGenerationTool(ToolBase):
    """Gera arquivos SVG com visualizações agregadas de SRAG."""

    name: str = "chart_generation"
    description: str = (
        "Gera gráficos prontos para uso no relatório epidemiológico. "
        "Use 'daily' para dados diários (últimos 30 dias) e 'monthly' para dados mensais."
    )
    args_schema: type[ChartGenerationInput] = ChartGenerationInput

    def _prepare_daily_series(self, data: Sequence[Dict[str, Any]]) -> List[tuple[datetime, float]]:
        series: List[tuple[datetime, float]] = []
        for entry in data:
            date_raw = entry.get("date")
            cases = entry.get("cases")
            if date_raw is None or cases is None:
                continue
            try:
                parsed_date = datetime.fromisoformat(str(date_raw))
            except ValueError:
                logger.warning("Data diária inválida ignorada: %s", date_raw)
                continue
            try:
                cases_value = float(cases)
            except (TypeError, ValueError):
                logger.warning("Número de casos inválido ignorado: %s", cases)
                continue
            series.append((parsed_date, cases_value))

        series.sort(key=lambda item: item[0])
        return series

    def _prepare_monthly_series(self, data: Sequence[Dict[str, Any]]) -> List[tuple[datetime, float]]:
        series: List[tuple[datetime, float]] = []
        for entry in data:
            month_raw = entry.get("month")
            cases = entry.get("cases")
            if month_raw is None or cases is None:
                continue
            try:
                parsed_date = datetime.strptime(str(month_raw) + "-01", "%Y-%m-%d")
            except ValueError:
                logger.warning("Mês inválido ignorado: %s", month_raw)
                continue
            try:
                cases_value = float(cases)
            except (TypeError, ValueError):
                logger.warning("Número de casos inválido ignorado: %s", cases)
                continue
            series.append((parsed_date, cases_value))

        series.sort(key=lambda item: item[0])
        return series

    def _build_line_chart(
        self,
        series: Sequence[tuple[datetime, float]],
        title: str,
        x_label: str,
        y_label: str,
        filename: Path,
        formatter: str,
    ) -> Path:
        if not series:
            raise ValueError("Não há dados suficientes para gerar o gráfico")

        x_values = [point for point, _ in series]
        y_values = [value for _, value in series]

        width, height = 900, 420
        margin_left, margin_right = 80, 30
        margin_top, margin_bottom = 70, 70
        chart_width = width - margin_left - margin_right
        chart_height = height - margin_top - margin_bottom

        min_value = min(y_values)
        max_value = max(y_values)
        if min_value == max_value:
            max_value = min_value + 1

        def scale_x(index: int) -> float:
            if len(series) == 1:
                return margin_left + chart_width / 2
            return margin_left + (index / (len(series) - 1)) * chart_width

        def scale_y(value: float) -> float:
            ratio = (value - min_value) / (max_value - min_value)
            return margin_top + (1 - ratio) * chart_height

        def format_label(dt_value: datetime) -> str:
            if formatter == "date":
                return dt_value.strftime("%d/%m")
            return dt_value.strftime("%m/%Y")

        points = [f"{scale_x(idx):.2f},{scale_y(val):.2f}" for idx, (_, val) in enumerate(series)]

        x_ticks = []
        tick_count = min(6, len(series)) if len(series) > 1 else 1
        for i in range(tick_count):
            index = 0 if tick_count == 1 else round(i * (len(series) - 1) / (tick_count - 1))
            dt_value, val = series[index]
            x_pos = scale_x(index)
            x_ticks.append((x_pos, format_label(dt_value)))

        y_ticks = []
        for i in range(5):
            value = min_value + (i / 4) * (max_value - min_value)
            y_pos = scale_y(value)
            y_ticks.append((y_pos, f"{value:.0f}"))

        svg_lines = [
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>",
            f"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"{width}\" height=\"{height}\" viewBox=\"0 0 {width} {height}\">",
            f"  <rect width=\"100%\" height=\"100%\" fill=\"#ffffff\" rx=\"12\" ry=\"12\" />",
            f"  <text x=\"{width/2:.1f}\" y=\"{margin_top/2:.1f}\" text-anchor=\"middle\" font-size=\"22\" font-weight=\"bold\" fill=\"#1b1b1b\">{title}</text>",
            f"  <text x=\"{width/2:.1f}\" y=\"{height - 20}\" text-anchor=\"middle\" font-size=\"16\" fill=\"#444444\">{x_label}</text>",
            f"  <text x=\"25\" y=\"{margin_top + chart_height/2:.1f}\" transform=\"rotate(-90 25,{margin_top + chart_height/2:.1f})\" text-anchor=\"middle\" font-size=\"16\" fill=\"#444444\">{y_label}</text>",
            f"  <line x1=\"{margin_left}\" y1=\"{margin_top}\" x2=\"{margin_left}\" y2=\"{margin_top + chart_height}\" stroke=\"#222\" stroke-width=\"2\" />",
            f"  <line x1=\"{margin_left}\" y1=\"{margin_top + chart_height}\" x2=\"{margin_left + chart_width}\" y2=\"{margin_top + chart_height}\" stroke=\"#222\" stroke-width=\"2\" />",
        ]

        # Grade horizontal
        for y_pos, label in y_ticks:
            svg_lines.append(
                f"  <line x1=\"{margin_left}\" y1=\"{y_pos:.2f}\" x2=\"{margin_left + chart_width}\" y2=\"{y_pos:.2f}\" stroke=\"#e0e0e0\" stroke-width=\"1\" />"
            )
            svg_lines.append(
                f"  <text x=\"{margin_left - 10}\" y=\"{y_pos + 5:.2f}\" text-anchor=\"end\" font-size=\"14\" fill=\"#555\">{label}</text>"
            )

        # Grade vertical + rótulos de data
        for x_pos, label in x_ticks:
            svg_lines.append(
                f"  <line x1=\"{x_pos:.2f}\" y1=\"{margin_top}\" x2=\"{x_pos:.2f}\" y2=\"{margin_top + chart_height}\" stroke=\"#f0f0f0\" stroke-width=\"1\" />"
            )
            svg_lines.append(
                f"  <text x=\"{x_pos:.2f}\" y=\"{margin_top + chart_height + 25}\" text-anchor=\"middle\" font-size=\"13\" fill=\"#555\">{label}</text>"
            )

        svg_lines.append(
            f"  <polyline points=\"{' '.join(points)}\" fill=\"none\" stroke=\"#1f77b4\" stroke-width=\"3\" stroke-linejoin=\"round\" stroke-linecap=\"round\" />"
        )

        for idx, (_, value) in enumerate(series):
            x_pos = scale_x(idx)
            y_pos = scale_y(value)
            svg_lines.append(
                f"  <circle cx=\"{x_pos:.2f}\" cy=\"{y_pos:.2f}\" r=\"4\" fill=\"#1f77b4\" />"
            )

        svg_lines.append(
            f"  <text x=\"{width - 10}\" y=\"{margin_top}\" text-anchor=\"end\" font-size=\"12\" fill=\"#777\">Atualizado em {datetime.now().strftime('%d/%m/%Y %H:%M')}</text>"
        )
        svg_lines.append("</svg>")

        filename.parent.mkdir(parents=True, exist_ok=True)
        filename.write_text("\n".join(svg_lines), encoding="utf-8")

        logger.info("Gráfico salvo em: %s", filename)
        return filename

    def _generate_daily_chart(self, data: List[Dict[str, Any]], output_dir: Path) -> Path:
        series = self._prepare_daily_series(data)
        filename = output_dir / "casos_diarios.svg"
        return self._build_line_chart(
            series,
            title="Casos de SRAG - Últimos 30 dias",
            x_label="Data",
            y_label="Número de casos",
            filename=filename,
            formatter="date",
        )

    def _generate_monthly_chart(self, data: List[Dict[str, Any]], output_dir: Path) -> Path:
        series = self._prepare_monthly_series(data)
        filename = output_dir / "casos_mensais.svg"
        return self._build_line_chart(
            series,
            title="Casos de SRAG - Últimos 12 meses",
            x_label="Mês",
            y_label="Número de casos",
            filename=filename,
            formatter="month",
        )

    def _run(
        self,
        chart_type: str,
        data: str,
        output_path: str = str(REPORTS_DIR),
    ) -> Dict[str, Any]:
        """Gera um gráfico em SVG com base nos dados informados."""

        logger.info("Gerando gráfico tipo: %s", chart_type)

        try:
            data_obj = json.loads(data) if isinstance(data, str) else data

            if not isinstance(data_obj, list):
                raise ValueError("Dados de gráfico devem ser uma lista de pontos")

            output_dir = ensure_directory(resolve_path(output_path))

            if chart_type == "daily":
                filename = self._generate_daily_chart(data_obj, output_dir)
            elif chart_type == "monthly":
                filename = self._generate_monthly_chart(data_obj, output_dir)
            else:
                return {"success": False, "error": f"Tipo de gráfico inválido: {chart_type}"}

            relative_name: str
            try:
                relative_name = str(filename.relative_to(output_dir))
            except ValueError:
                relative_name = filename.name

            return {
                "success": True,
                "chart_type": chart_type,
                "filename": relative_name,
                "path": str(filename),
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as exc:
            logger.error("Erro ao gerar gráfico: %s", exc)
            return {
                "success": False,
                "error": str(exc),
            }
    
    async def _arun(self, chart_type: str, data: str, output_path: str = "") -> Dict[str, Any]:
        """Versão assíncrona (não implementada)."""
        raise NotImplementedError("Versão assíncrona não implementada")


def create_chart_tool() -> ChartGenerationTool:
    """Cria e retorna uma instância da ferramenta de gráficos."""
    return ChartGenerationTool()


if __name__ == "__main__":
    import json
    
    # Teste da ferramenta
    tool = create_chart_tool()
    
    # Dados de teste para gráfico diário
    daily_data = [
        {"date": "2024-12-24", "cases": 298},
        {"date": "2024-12-25", "cases": 209},
        {"date": "2024-12-26", "cases": 719},
        {"date": "2024-12-27", "cases": 614},
        {"date": "2024-12-28", "cases": 261},
        {"date": "2024-12-29", "cases": 202},
        {"date": "2024-12-30", "cases": 697},
    ]
    
    # Dados de teste para gráfico mensal
    monthly_data = [
        {"month": "2024-10", "cases": 19915},
        {"month": "2024-11", "cases": 17564},
        {"month": "2024-12", "cases": 16920}
    ]
    
    print("\n=== Teste: Gráfico Diário ===")
    result = tool._run(chart_type="daily", data=json.dumps(daily_data))
    print(result)
    
    print("\n=== Teste: Gráfico Mensal ===")
    result = tool._run(chart_type="monthly", data=json.dumps(monthly_data))
    print(result)
