# Citation Styles Reference

Formatting guidelines for the common academic citation styles. Pick **one** style for a given review (default to numbered Vancouver/Nature-style `[n]` unless the user names a target venue) and apply it consistently throughout — both the in-text markers and the reference list.

## APA Style (7th Edition)

**Journal article**: Author, A. A., Author, B. B., & Author, C. C. (Year). Title of article. *Title of Periodical*, *volume*(issue), page range. https://doi.org/xx.xxx/yyyy

**Example**: Smith, J. D., Johnson, M. L., & Williams, K. R. (2023). Machine learning approaches in drug discovery. *Nature Reviews Drug Discovery*, *22*(4), 301-318. https://doi.org/10.1038/nrd.2023.001

**Preprint**: Author, A. A. (Year). Title of preprint. *Repository Name*. https://doi.org/xxxx

**In-text**: (Smith et al., 2023); Smith et al. (2023) demonstrated…; multiple: (Brown, 2022; Smith et al., 2023)

## Nature Style

**Journal article**: Author, A. A., Author, B. B. & Author, C. C. Title of article. *J. Name* **volume**, page range (year).

**Example**: Smith, J. D., Johnson, M. L. & Williams, K. R. Machine learning approaches in drug discovery. *Nat. Rev. Drug Discov.* **22**, 301-318 (2023).

**Authors**: 1-2 → list all; 3+ → first author + "et al." **In-text**: superscript numbers, e.g. studies^1,2^.

## Vancouver Style (Numbered)

**Journal article**: Author AA, Author BB, Author CC. Title of article. Abbreviated Journal Name. Year;volume(issue):page range.

**Example**: Smith JD, Johnson ML, Williams KR. Machine learning approaches in drug discovery. Nat Rev Drug Discov. 2023;22(4):301-18.

**In-text**: superscript numbers in order of appearance: studies^1,2^.

## IEEE Style

**Journal article**: [#] A. A. Author, B. B. Author, and C. C. Author, "Title of article," *Abbreviated Journal Name*, vol. x, no. x, pp. xxx-xxx, Month Year.

**Example**: [1] J. D. Smith, M. L. Johnson, and K. R. Williams, "Machine learning approaches in drug discovery," *Nat. Rev. Drug Discov.*, vol. 22, no. 4, pp. 301-318, Apr. 2023.

## Chicago Style (Author-Date)

**Journal article**: Author, First M. Year. "Article Title." *Journal Title* volume, no. issue (Month): page range. https://doi.org/xxxx.

---

## DOI best practices

1. **Always verify DOIs** with `scripts/verify_citations.py` before finalizing — it flags DOIs that don't resolve and shows the CrossRef title so you can catch a DOI that points at the wrong paper.
2. **Format as URLs**: `https://doi.org/10.xxxx/yyyy` (preferred over `doi:10.xxxx/yyyy`).
3. **No trailing period** after a DOI URL.
4. **Resolve redirects**: confirm the DOI lands on the correct article.

## Reference list organization

- **APA, Chicago** → alphabetical by first author's surname.
- **Nature, Vancouver, IEEE** → numerical, in order of first appearance in text.
- Keep capitalization, journal abbreviations, DOI presentation, and author-name format consistent throughout.

## Common journal abbreviations

Nature → Nat. · Nature Reviews Drug Discovery → Nat. Rev. Drug Discov. · Proceedings of the National Academy of Sciences → Proc. Natl. Acad. Sci. U.S.A. · Journal of the American Chemical Society → J. Am. Chem. Soc. · Nucleic Acids Research → Nucleic Acids Res. · PLOS ONE → PLoS ONE. (Science, Cell, Bioinformatics keep their names.)
