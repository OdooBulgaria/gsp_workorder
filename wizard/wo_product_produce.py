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
import openerp.addons.decimal_precision as dp

class stock_move_consume(osv.osv_memory):
    _inherit = "stock.move.consume"
    _description = "GSP Consume Products"
    
    def do_move_consume(self, cr, uid, ids, context=None):
        if context is None:
            context = {}
        move_obj = self.pool.get('stock.move')
        uom_obj = self.pool.get('product.uom')
        move_ids = context['active_ids']
        for data in self.browse(cr, uid, ids, context=context):
            if move_ids and move_ids[0]:
                move = move_obj.browse(cr, uid, move_ids[0], context=context)
            qty = uom_obj._compute_qty(cr, uid, data['product_uom'].id, data.product_qty, data.product_id.uom_id.id)
            move_obj.action_consume(cr, uid, move_ids,
                             qty, data.location_id.id, restrict_lot_id=data.restrict_lot_id.id,
                             context=context)
        return {'type': 'ir.actions.act_window_close'}

class mrp_product_produce_line(osv.osv_memory):
    _inherit="mrp.product.produce.line"
    _description = "GSP Product Produce Consume lines"

    _columns = {
                'wo_id':fields.many2one('wo.product.produce')
                }
    
class wo_product_produce(osv.osv_memory):
    _name = 'wo.product.produce'
    _description = 'Pop finish wizard'

    
    def do_produce(self, cr, uid, ids, context=None):
        consume = self.pool.get('stock.move.consume')
        prod_obj_pool = self.pool.get('mrp.production')
        move_obj = self.pool.get('stock.move')
        if context and context.get("line_id"):
            cr.execute('''
            select distinct(production_id) from mrp_production_workcenter_line where id = %s
            ''' %(context.get('line_id',False)))
            
        prod_obj = self.pool.get('mrp.production').browse(cr,uid,cr.fetchone()[0],context)
                   
        cr.execute('''
        select distinct stock_move.id,mrp_product_produce_line.wo_id,mrp_product_produce_line.product_qty,mrp_product_produce_line.lot_id,mrp_product_produce_line.product_id,stock_move.product_uom,location_id from stock_move left join mrp_product_produce_line on stock_move.product_id = mrp_product_produce_line.product_id where stock_move.raw_material_production_id = %s and stock_move.state not in ('done','cancel') and mrp_product_produce_line.wo_id = %s 
        ''' %(prod_obj.id,ids[0]))
        
        detail = cr.fetchall()
        
        for move in detail:
            if move[2] != 0 :
                move_obj.write(cr,uid,move[0],{'product_uom_qty':move[2]},context)

        if prod_obj.state =='confirmed':
            prod_obj_pool.force_production(cr, uid, [prod_obj.id])
            prod_obj_pool.signal_workflow(cr, uid, [prod_obj.id], 'button_produce')             
        elif prod_obj.state =='ready':
            prod_obj_pool.signal_workflow(cr, uid, [prod_obj.id], 'button_produce')
        elif prod_obj.state =='in_production':
            pass
        else:
            raise osv.except_osv(_('Error!'),_('Manufacturing order cannot be started in state "%s"!') % (prod_obj.state,))

        
        for line in detail:
            if not(line[2] == 0): 
                consume_id = consume.create(cr,uid,{
                                                'product_id':line[4],
                                                'restrict_lot_id':line[3],
                                                'product_qty':line[2],
                                                'product_uom':line[5],
                                                'location_id':line[6]
                                                },context)
                context.update({'active_ids':[line[0]],'active_id':line[0],'consume':True,'search_disable_custom_filters': True,})
                consume.do_move_consume(cr, uid, [consume_id], context=context)
        return True
    
    def _get_product_ids(self, cr, uid, context=None):
        """ To obtain product id
        @return: id
        """
        prod=False
        if context and context.get("line_id"):
            cr.execute('''
            select distinct(production_id) from mrp_production_workcenter_line where id = %s
            ''' %(context.get('line_id',False)))
            prod = self.pool.get('mrp.production').browse(cr, uid,
                                    cr.fetchone()[0], context=context)
        return prod and prod.product_id.id or False
    
    def _get_tracks(self, cr, uid, context=None):
        prod = self._get_product_ids(cr, uid, context=context)
        prod_obj = self.pool.get("product.product")
        return prod and prod_obj.browse(cr, uid, prod, context=context).track_production or False
   


    def _get_product_qtys(self, cr, uid, context=None):
        """ To obtain product quantity
        @param self: The object pointer.
        @param cr: A database cursor
        @param uid: ID of the user currently logged in
        @param context: A standard dictionary
        @return: Quantity
        """
        if context is None:
            context = {}
        if context and context.get("line_id"):
            cr.execute('''
            select distinct(production_id) from mrp_production_workcenter_line where id = %s
            ''' %(context.get('line_id',False)))
            prod = self.pool.get('mrp.production').browse(cr, uid,
                                    cr.fetchone()[0], context=context)
        done = 0.0
        for move in prod.move_created_ids2:
            if move.product_id == prod.product_id:
                if not move.scrapped:
                    done += move.product_uom_qty # As uom of produced products and production order should correspond
        return prod.product_qty - done


 
    def on_change_qty(self, cr, uid, ids, product_qty, consume_lines, context=None):
        """ 
            When changing the quantity of products to be produced it will 
            recalculate the number of raw materials needed according
            to the scheduled products and the already consumed/produced products
            It will return the consume lines needed for the products to be produced
            which the user can still adapt
        """
        prod_obj = self.pool.get("mrp.production")
        uom_obj = self.pool.get("product.uom")
        if context and context.get("line_id"):
            cr.execute('''
            select distinct(production_id) from mrp_production_workcenter_line where id = %s
            ''' %(context.get('line_id',False)))
            production = self.pool.get('mrp.production').browse(cr, uid,
                                    cr.fetchone()[0], context=context)
        consume_lines = []
        new_consume_lines = []
        if product_qty > 0.0:
            product_uom_qty = uom_obj._compute_qty(cr, uid, production.product_uom.id, product_qty, production.product_id.uom_id.id)
            consume_lines = prod_obj._calculate_qty(cr, uid, production, product_qty=product_uom_qty, context=context)                
        
        for consume in consume_lines:
            new_consume_lines.append([0, False, consume])
        return {'value': {'consume_lines': new_consume_lines}}
    
    _columns = {
                'track_production': fields.boolean('Track production'),
                'product_id': fields.many2one('product.product', type='many2one'),
                'product_qty': fields.float('Select Quantity', digits_compute=dp.get_precision('Product Unit of Measure'), required=True),
                'mode': fields.selection([('consume_produce', 'Consume & Produce'),
                                  ('consume', 'Consume Only')], 'Mode', required=True,
                                  help="'Consume only' mode will only consume the products with the quantity selected.\n"
                                        "'Consume & Produce' mode will consume as well as produce the products with the quantity selected "
                                        "and it will finish the production order when total ordered quantities are produced."),
                'lot_id': fields.many2one('stock.production.lot', 'Lot'), #Should only be visible when it is consume and produce mode
                'consume_lines': fields.one2many('mrp.product.produce.line', 'wo_id', 'Products Consumed'),

                }
    _defaults = {
                 'mode': lambda *x: 'consume_produce',
                 'product_id':_get_product_ids,
                 'product_qty':_get_product_qtys,
                 'track_production': _get_tracks, 
                 }    