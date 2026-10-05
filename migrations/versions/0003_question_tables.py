"""show the two data tables (Οικονομικές Επιστήμες #150, #197) as table markup

The question text marks a table with "| cell | cell |" rows; a "|---|---|"
row under the first one makes it a header. static/app.js renders it.
Only rows still holding the original text are changed, so admin edits stay.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-05

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None

# question id -> (text before, text after)
TABLES = {
    "oikonomikes-epistimes-150": (
        # before
        'Στον παρακάτω πίνακα παρουσιάζονται τα κλιμάκια φορολογητέου εισοδήματος και οι αντίστοιχοι οριακοί φορολογικοί συντελεστές.\n'
        'Κλιμάκια φορολογητέου εισοδήματος (€) — Οριακός φορολογικός συντελεστής (%)\n'
        '0 – 10.000 — 10\n'
        '10.001 – 30.000 — 20\n'
        '30.001 και άνω — 40\n'
        'Η φορολογία στο εν λόγω παράδειγμα χαρακτηρίζεται ως:',
        # after
        'Στον παρακάτω πίνακα παρουσιάζονται τα κλιμάκια φορολογητέου εισοδήματος και οι αντίστοιχοι οριακοί φορολογικοί συντελεστές.\n'
        '| Κλιμάκια Φορολογητέου Εισοδήματος (€) | Οριακός Φορολογικός Συντελεστής (%) |\n'
        '|---|---|\n'
        '| 0 – 10.000 | 10 |\n'
        '| 10.001 – 30.000 | 20 |\n'
        '| 30.001 και άνω | 40 |\n'
        'Η φορολογία στο εν λόγω παράδειγμα χαρακτηρίζεται ως:',
    ),
    "oikonomikes-epistimes-197": (
        # before
        'Για τις χώρες Α, Β, Γ και Δ υπολογίστηκε ο συντελεστής Gini για το προσωπικό εισόδημα ως ακολούθως:\n'
        'Χώρα Α: 0,38\n'
        'Χώρα Β: 0,45\n'
        'Χώρα Γ: 0,42\n'
        'Χώρα Δ: 0,40\n'
        'Σε ποια από τέσσερις χώρες είναι πιθανό να αντιστοιχεί μεγαλύτερη οικονομική ανισότητα;',
        # after
        'Για τις χώρες Α, Β, Γ και Δ υπολογίστηκε ο συντελεστής Gini για το προσωπικό εισόδημα ως ακολούθως:\n'
        '| Χώρα Α | 0,38 |\n'
        '| Χώρα Β | 0,45 |\n'
        '| Χώρα Γ | 0,42 |\n'
        '| Χώρα Δ | 0,40 |\n'
        'Σε ποια από τέσσερις χώρες είναι πιθανό να αντιστοιχεί μεγαλύτερη οικονομική ανισότητα;',
    ),
}

_UPDATE = sa.text("UPDATE question SET text = :new WHERE id = :id AND text = :old")


def upgrade():
    bind = op.get_bind()
    for qid, (before, after) in TABLES.items():
        bind.execute(_UPDATE, {"id": qid, "old": before, "new": after})


def downgrade():
    bind = op.get_bind()
    for qid, (before, after) in TABLES.items():
        bind.execute(_UPDATE, {"id": qid, "old": after, "new": before})
