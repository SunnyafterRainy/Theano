from __future__ import absolute_import, print_function, division
import numpy as np

import theano
from theano import Op, Apply, scalar
from theano.tensor import TensorType
from theano.gof.type import CDataType, EnumType, EnumList

from nose.plugins.skip import SkipTest

# todo: test generic


class ProdOp(Op):
    __props__ = ()

    def make_node(self, i):
        return Apply(self, [i], [CDataType('void *', 'py_decref')()])

    def c_support_code(self):
        return """
void py_decref(void *p) {
  Py_XDECREF((PyObject *)p);
}
"""

    def c_code(self, node, name, inps, outs, sub):
        return """
Py_XDECREF(%(out)s);
%(out)s = (void *)%(inp)s;
Py_INCREF(%(inp)s);
""" % dict(out=outs[0], inp=inps[0])

    def c_code_cache_version(self):
        return (0,)


class GetOp(Op):
    __props__ = ()

    def make_node(self, c):
        return Apply(self, [c], [TensorType('float32', (False,))()])

    def c_support_code(self):
        return """
void py_decref(void *p) {
  Py_XDECREF((PyObject *)p);
}
"""

    def c_code(self, node, name, inps, outs, sub):
        return """
Py_XDECREF(%(out)s);
%(out)s = (PyArrayObject *)%(inp)s;
Py_INCREF(%(out)s);
""" % dict(out=outs[0], inp=inps[0])

    def c_code_cache_version(self):
        return (0,)


def test_cdata():
    if not theano.config.cxx:
        raise SkipTest("G++ not available, so we need to skip this test.")
    i = TensorType('float32', (False,))()
    c = ProdOp()(i)
    i2 = GetOp()(c)
    mode = None
    if theano.config.mode == "FAST_COMPILE":
        mode = "FAST_RUN"

    # This should be a passthrough function for vectors
    f = theano.function([i], i2, mode=mode)

    v = np.random.randn(9).astype('float32')

    v2 = f(v)
    assert (v2 == v).all()


class TestOpEnumList(Op):
    __props__ = ('op_chosen',)
    params_type = EnumList('ADD', 'SUB', 'MULTIPLY', 'DIVIDE')

    def __init__(self, choose_op):
        assert self.params_type.ADD == 0
        assert self.params_type.SUB == 1
        assert self.params_type.MULTIPLY == 2
        assert self.params_type.DIVIDE == 3
        op_to_const = {'+': self.params_type.ADD,
                       '-': self.params_type.SUB,
                       '*': self.params_type.MULTIPLY,
                       '/': self.params_type.DIVIDE}
        self.op_chosen = op_to_const[choose_op]

    def get_params(self, node):
        return self.op_chosen

    def make_node(self, a, b):
        return Apply(self, [scalar.as_scalar(a), scalar.as_scalar(b)], [scalar.float64()])

    def perform(self, node, inputs, outputs, op):
        a, b = inputs
        o, = outputs
        if op == self.params_type.ADD:
            o[0] = a + b
        elif op == self.params_type.SUB:
            o[0] = a - b
        elif op == self.params_type.MULTIPLY:
            o[0] = a * b
        elif op == self.params_type.DIVIDE:
            o[0] = a / b
        else:
            raise NotImplementedError('Unknown op id ' + str(op))

    def c_code_cache_version(self):
        return (1,)

    def c_code(self, node, name, inputs, outputs, sub):
        a, b = inputs
        o, = outputs
        fail = sub['fail']
        op = sub['params']
        return """
        switch((int)%(op)s) {
            case ADD:
                %(o)s = %(a)s + %(b)s;
                break;
            case SUB:
                %(o)s = %(a)s - %(b)s;
                break;
            case MULTIPLY:
                %(o)s = %(a)s * %(b)s;
                break;
            case DIVIDE:
                %(o)s = %(a)s / %(b)s;
                break;
            default:
                {%(fail)s}
                break;
        }
        """ % locals()


def test_enum():
    # Check that invalid enum name raises exception.
    for invalid_name in ('a', '_A', '0'):
        try:
            EnumList(invalid_name)
        except AttributeError:
            pass
        else:
            raise Exception('EnumList with invalid name should faild.')

        try:
            EnumType(**{invalid_name: 0})
        except AttributeError:
            pass
        else:
            raise Exception('EnumType with invalid name should fail.')

    # Check that invalid enum value raises exception.
    try:
        EnumType(INVALID_VALUE='string is not allowe.')
    except ValueError:
        pass
    else:
        raise Exception('EnumType with invalid value should fail.')

    # Check EnumType.
    e1 = EnumType(C1=True, C2=12, C3=True, C4=-1, C5=False, C6=0.0)
    e2 = EnumType(C1=1, C2=12, C3=1, C4=-1.0, C5=0.0, C6=0)
    assert e1 == e2
    assert not (e1 != e2)
    assert hash(e1) == hash(e2)

    # Test an op with EnumList.
    a = scalar.int32()
    b = scalar.int32()
    c_add = TestOpEnumList('+')(a, b)
    c_sub = TestOpEnumList('-')(a, b)
    c_multiply = TestOpEnumList('*')(a, b)
    c_divide = TestOpEnumList('/')(a, b)
    f = theano.function([a, b], [c_add, c_sub, c_multiply, c_divide])
    va = 12
    vb = 15
    ref_add = va + vb
    ref_sub = va - vb
    ref_multiply = va * vb
    ref_divide = va // vb
    ref = [ref_add, ref_sub, ref_multiply, ref_divide]
    out = f(va, vb)
    assert ref == out, (ref, out)
