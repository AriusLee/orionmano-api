"""Skill implementations. Import this module to register all skills."""

from app.services.agent.skills.generate_report import (
    GenerateGapAnalysisSkill,
    GenerateIndustryReportSkill,
    GenerateDDReportSkill,
    GenerateValuationReportSkill,
    GenerateTeaserSkill,
)
from app.services.agent.skills.generate_deck import (
    GenerateSalesDeckSkill,
    GenerateKickoffDeckSkill,
    GenerateTeaserDeckSkill,
    GenerateCompanyDeckSkill,
)
from app.services.agent.skills.web_research import WebResearchSkill
from app.services.agent.skills.analyze_financials import AnalyzeFinancialsSkill
from app.services.agent.skills.extract_document import ExtractDocumentSkill
from app.services.agent.skills.executive_summary import ExecutiveSummarySkill
from app.services.agent.skills.produce_valuation_inputs import ProduceValuationInputsSkill
from app.services.agent.skills.generate_valuation_workpaper import (
    GenerateValuationWorkpaperSkill,
)
from app.services.agent.registry import register_skill

# Reports (5 types)
register_skill(GenerateGapAnalysisSkill())
register_skill(GenerateIndustryReportSkill())
register_skill(GenerateDDReportSkill())
register_skill(GenerateValuationReportSkill())
register_skill(GenerateTeaserSkill())

# Decks (4 types)
register_skill(GenerateSalesDeckSkill())
register_skill(GenerateKickoffDeckSkill())
register_skill(GenerateTeaserDeckSkill())
register_skill(GenerateCompanyDeckSkill())

# Other skills
register_skill(WebResearchSkill())
register_skill(AnalyzeFinancialsSkill())
register_skill(ExtractDocumentSkill())
register_skill(ExecutiveSummarySkill())

# Valuation workpaper pipeline
register_skill(ProduceValuationInputsSkill())
register_skill(GenerateValuationWorkpaperSkill())
