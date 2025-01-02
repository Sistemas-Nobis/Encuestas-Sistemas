"""Columna de promedio y porcentaje - Fix

Revision ID: db947c1ef0f3
Revises: db07cb87e03d
Create Date: 2024-12-27 13:16:13.230661

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'db947c1ef0f3'
down_revision = 'db07cb87e03d'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('respuesta', schema=None) as batch_op:
        batch_op.add_column(sa.Column('promedio_respuestas', sa.String(length=4), nullable=False))
        batch_op.add_column(sa.Column('porcentaje_respuestas', sa.Integer(), nullable=False))
        batch_op.drop_column('suma_respuestas')

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('respuesta', schema=None) as batch_op:
        batch_op.add_column(sa.Column('suma_respuestas', sa.INTEGER(), nullable=False))
        batch_op.drop_column('porcentaje_respuestas')
        batch_op.drop_column('promedio_respuestas')

    # ### end Alembic commands ###