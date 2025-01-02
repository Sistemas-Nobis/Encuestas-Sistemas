"""Ajustes en tipos de datos

Revision ID: 10bb5ff2c31a
Revises: db947c1ef0f3
Create Date: 2024-12-27 14:26:01.939809

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '10bb5ff2c31a'
down_revision = 'db947c1ef0f3'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('respuesta', schema=None) as batch_op:
        batch_op.add_column(sa.Column('nivel', sa.String(length=10), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('respuesta', schema=None) as batch_op:
        batch_op.drop_column('nivel')

    # ### end Alembic commands ###
