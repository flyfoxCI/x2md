"""Canonical platform-specific contracts for professional research reports."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ResearchTemplate:
    """The exact report structure and research lens for one source platform."""

    platform: str
    label: str
    focus: str
    headings: tuple[str, ...]
    citation_required_headings: tuple[str, ...]

    def markdown_skeleton(self) -> str:
        """Render the exact level-two heading skeleton expected from the model."""
        return "\n\n".join(f"## {heading}" for heading in self.headings) + "\n"


_COMMON_OPENING = ("研究摘要", "一图综述", "研究范围与证据质量")
_COMMON_CLOSING = ("结论", "标签", "证据索引")
_STRUCTURAL_HEADINGS = {"一图综述", "研究范围与证据质量", "标签", "证据索引"}


def _template(
    platform: str,
    label: str,
    focus: str,
    body_headings: tuple[str, ...],
) -> ResearchTemplate:
    headings = _COMMON_OPENING + body_headings + _COMMON_CLOSING
    return ResearchTemplate(
        platform=platform,
        label=label,
        focus=focus,
        headings=headings,
        citation_required_headings=tuple(
            heading for heading in headings if heading not in _STRUCTURAL_HEADINGS
        ),
    )


_TEMPLATES = {
    "github": _template(
        "github",
        "GitHub 项目工程研究",
        (
            "像资深软件架构师与研究工程师一样解释项目。重点回答项目解决什么问题、"
            "核心能力为何成立、模块怎样协作、关键机制如何实现、工程成熟度如何、"
            "何时值得采用，以及它对后续研发有什么启发。不要把 README 改写成摘要。"
        ),
        (
            "项目定位与问题",
            "核心能力与差异化",
            "系统架构与模块边界",
            "关键流程与实现机制",
            "工程质量与可复现性",
            "应用场景与采用建议",
            "局限、风险与未验证假设",
            "研究启发与关联方向",
        ),
    ),
    "arxiv": _template(
        "arxiv",
        "arXiv 论文研究",
        (
            "像领域研究者一样重建论文的研究逻辑。区分作者主张与证据，解释方法原理、"
            "算法或模型流程、实验协议、基线与消融、结论的有效范围，并指出开放问题、"
            "相关工作脉络和可复现路径。不要按章节机械复述摘要。"
        ),
        (
            "研究问题与论文主张",
            "方法原理与关键创新",
            "模型或算法流程",
            "实验设计与评估协议",
            "结果、对比与消融",
            "结论有效范围",
            "局限、风险与开放问题",
            "研究启发与相关工作脉络",
            "复现与后续研究建议",
        ),
    ),
    "huggingface": _template(
        "huggingface",
        "Hugging Face 技术内容研究",
        (
            "像技术研究编辑一样分析博客、模型、数据集或 Space。解释目标读者与价值主张、"
            "技术路线和工件用法，判断案例与结果的证据强度，梳理它同代码、论文、模型及"
            "数据的关系，并给出实践边界与延伸研究方向。不要把页面文案重新排版。"
        ),
        (
            "内容定位与目标读者",
            "核心观点与价值主张",
            "技术路线或产品机制",
            "工件、配置与使用方式",
            "案例、结果与证据强度",
            "与代码、论文、模型或数据的关系",
            "适用场景与实践建议",
            "局限、风险与信息缺口",
            "研究启发与延伸阅读方向",
        ),
    ),
}


def research_template(platform: str) -> ResearchTemplate:
    """Return the canonical report contract for a supported research platform."""
    try:
        return _TEMPLATES[platform.strip().lower()]
    except KeyError as error:
        raise ValueError(f"unsupported research platform: {platform}") from error
