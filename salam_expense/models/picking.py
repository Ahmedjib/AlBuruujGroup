# -*- coding: utf-8 -*-

from odoo import api, models, fields, _
from odoo.exceptions import ValidationError
from odoo.exceptions import UserError

class ApprovalLevel(models.Model):
    _name = 'approval.level'
    _description = 'Approval Level'
    _order = 'level'

    name = fields.Char('Name')
    level = fields.Integer('Level')
    is_last_approval = fields.Boolean('Is Last')
    is_reject = fields.Boolean('Is Reject')
    approval_user_id = fields.Many2one('res.users', string='Approval User')


class Picking(models.Model):
    _inherit = "stock.picking"

    is_expense = fields.Boolean('Is Expense')

    def get_expense_operation_type(self):
        expense_operation_type_id = self.env['stock.picking.type'].search([('sequence_code', '=', 'EXP')])
        return expense_operation_type_id.id
    expense_picking_type_id = fields.Many2one('stock.picking.type', string='Expense Operation Type', default=get_expense_operation_type)
    employee_id = fields.Many2one('hr.employee', 'Employee')

    def button_validate(self):
        for rec in self:
            rec.product_id.old_categ_id = rec.product_id.categ_id.id
            rec.product_id.categ_id = self.env.ref("salam_expense.product_category_expense_transfer").id
        res = super(Picking, self).button_validate()
        for rec in self:
            rec.product_id.categ_id = rec.product_id.old_categ_id
        return res


    @api.depends('next_approval_id', 'next_approval_id.approval_user_id')
    def _compute_next_approval_user_id(self):
        for rec in self:
            rec.next_approval_user_id = rec.next_approval_id.approval_user_id.id

    @api.depends('next_approval_id', 'next_approval_user_id')
    def _compute_is_button(self):
        for rec in self:
            if rec.next_approval_user_id.id == self.env.user.id:
                rec.is_button = True
            else:
                rec.is_button = False

            if rec.next_approval_id.is_last_approval or rec.next_approval_id.is_reject:
                rec.is_button = False
            if rec.next_approval_id.is_last_approval:
                rec.is_last_lavel = True
            else:
                rec.is_last_lavel = False


    def _get_next_approval_id(self):
        rec = self.env['approval.level'].search([('level', '=', 1)])
        return rec.id

    next_approval_id = fields.Many2one('approval.level', string='Next Approval', required=1, tracking=True,
                                       default=_get_next_approval_id)
    next_approval_user_id = fields.Many2one('res.users', string='Next Approval User',
                                            compute='_compute_next_approval_user_id', store=True)
    is_button = fields.Boolean('Is button', compute='_compute_is_button')
    is_last_lavel = fields.Boolean('Is button', compute='_compute_is_button')

    property_valuation = fields.Selection([
        ('manual_periodic', 'Manual'),
        ('real_time', 'Automated')], string='Inventory Valuation',
        default="real_time",
        company_dependent=True, copy=True, required=True,
        help="""Manual: The accounting entries to value the inventory are not posted automatically.
            Automated: An accounting entry is automatically created to value the inventory when a product enters or leaves the company.
            """)

    property_stock_journal = fields.Many2one(
        'account.journal', 'Stock Journal', company_dependent=True,
        domain="[('company_id', '=', allowed_company_ids[0])]", check_company=True,
        help="When doing automated inventory valuation, this is the Accounting Journal in which entries will be automatically posted when stock moves are processed.")
    property_stock_account_input_categ_id = fields.Many2one(
        'account.account', 'Stock Input Account', company_dependent=True,
        domain="[('company_id', '=', allowed_company_ids[0]), ('deprecated', '=', False)]", check_company=True,
        help="""Counterpart journal items for all incoming stock moves will be posted in this account, unless there is a specific valuation account
                    set on the source location. This is the default value for all products in this category. It can also directly be set on each product.""")
    property_stock_account_output_categ_id = fields.Many2one(
        'account.account', 'Stock Output Account', company_dependent=True,
        domain="[('company_id', '=', allowed_company_ids[0]), ('deprecated', '=', False)]", check_company=True,
        help="""When doing automated inventory valuation, counterpart journal items for all outgoing stock moves will be posted in this account,
                    unless there is a specific valuation account set on the destination location. This is the default value for all products in this category.
                    It can also directly be set on each product.""")
    property_stock_valuation_account_id = fields.Many2one(
        'account.account', 'Stock Valuation Account', company_dependent=True,
        domain="[('company_id', '=', allowed_company_ids[0]), ('deprecated', '=', False)]", check_company=True,
        help="""When automated inventory valuation is enabled on a product, this account will hold the current value of the products.""", )

    @api.constrains('property_stock_valuation_account_id', 'property_stock_account_output_categ_id',
                    'property_stock_account_input_categ_id')
    def _check_valuation_accouts(self):
        # Prevent to set the valuation account as the input or output account.
        for rec in self:
            valuation_account = rec.property_stock_valuation_account_id
            input_and_output_accounts = rec.property_stock_account_input_categ_id | rec.property_stock_account_output_categ_id
            if valuation_account and valuation_account in input_and_output_accounts:
                raise ValidationError(
                    _('The Stock Input and/or Output accounts cannot be the same as the Stock Valuation account.'))

    def action_approve(self):
        view_id = self.env.ref('salam_expense.remark_remark_wizard_wizard_view').id
        return {'type': 'ir.actions.act_window',
                'name': _('Remarks'),
                'res_model': 'remark.remark.wizard',
                'target': 'new',
                'view_mode': 'form',
                'views': [[view_id, 'form']],
                }

    @api.onchange('is_expense')
    def onchange_is_expense(self):
        for rec in self:
            if rec.is_expense:
                return {'domain': {'picking_type_id': [('id', '=', rec.expense_picking_type_id.id)]}}

    def sh_cancel(self):
        is_internal_transfer = any(picking.is_expense for picking in self)
        if not is_internal_transfer:
            self.unlink()
            return {
                'name': 'Transfers',
                'type': 'ir.actions.act_window',
                'res_model': 'stock.picking',
                'view_type': 'form',
                'view_mode': 'tree,kanban,form,calendar',
                'search_view_id': [self.env.ref('stock.view_picking_internal_search').id],
                'domain': [('is_expense', '!=', True)],
                'target': 'current',
            }
        super(Picking, self).sh_cancel()
        domain = [('is_expense', '=', True)]
        return {
            'name': 'Expense Transfers',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'view_type': 'form',
            'view_mode': 'tree,kanban,form,calendar',
            'search_view_id': [self.env.ref('stock.view_picking_internal_search').id],
            'domain': domain,
            'target': 'current',
        }

class StockMove(models.Model):
    _inherit = "stock.move"

    def _get_accounting_data_for_valuation(self):
        """ Return the accounts and journal to use to post Journal Entries for
        the real-time valuation of the quant. """
        self.ensure_one()
        self = self.with_company(self.company_id)

        accounts_data = self.product_id.product_tmpl_id.with_context(is_expense=self.picking_id.is_expense, picking_id=self.picking_id).get_product_accounts()

        acc_src = self._get_src_account(accounts_data)
        acc_dest = self._get_dest_account(accounts_data)

        acc_valuation = accounts_data.get('stock_valuation', False)
        if acc_valuation:
            acc_valuation = acc_valuation.id
        if not accounts_data.get('stock_journal', False):
            raise UserError(_('You don\'t have any stock journal defined on your product category, check if you have installed a chart of accounts.'))
        if not acc_src:
            raise UserError(_('Cannot find a stock input account for the product %s. You must define one on the product category, or on the location, before processing this operation.') % (self.product_id.display_name))
        if not acc_dest:
            raise UserError(_('Cannot find a stock output account for the product %s. You must define one on the product category, or on the location, before processing this operation.') % (self.product_id.display_name))
        if not acc_valuation:
            raise UserError(_('You don\'t have any stock valuation account defined on your product category. You must define one before processing this operation.'))
        journal_id = accounts_data['stock_journal'].id
        return journal_id, acc_src, acc_dest, acc_valuation
