# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2004-2010 Tiny SPRL (<http://tiny.be>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from openerp.osv import fields, osv
from openerp.tools.translate import _
import time
from datetime import datetime

class mrp_production_workcenter_line(osv.osv):
    _inherit = 'mrp.production.workcenter.line'
    _description = 'Pop finish wizard'


    def action_done(self, cr, uid, ids, context=None):
        delay = 0.0
        date_now = time.strftime('%Y-%m-%d %H:%M:%S')
        obj_line = self.browse(cr, uid, ids[0])
        date_start = datetime.strptime(obj_line.date_start,'%Y-%m-%d %H:%M:%S')
        date_finished = datetime.strptime(date_now,'%Y-%m-%d %H:%M:%S')
        delay += (date_finished-date_start).days * 24
        delay += (date_finished-date_start).seconds / float(60*60)
        self.write(cr, uid, ids, {'state':'done', 'date_finished': date_now,'delay':delay}, context=context)
#         self.modify_production_order_state(cr,uid,ids,'done')
#########################        
        view_ref = self.pool.get('ir.model.data').get_object_reference(cr, uid, 'gsp_workorder', 'view_wo_product_produce_wizard')
        view_id = view_ref and view_ref[1] or False
        workcenter_pool = self.pool.get('mrp.production.workcenter.line')
        workcenter_pool.signal_workflow(cr, uid, ids, 'button_done')
        return {
                'view_type': 'form',
                "view_mode": 'form',
                'view_id':view_id,
                'res_model': 'wo.product.produce',
                'type': 'ir.actions.act_window',
                'target': 'new',
                'context':{}
               }
        