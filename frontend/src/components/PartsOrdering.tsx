import { useState, useEffect } from 'react';
import { Search, ShoppingCart, AlertTriangle, Check } from 'lucide-react';

interface Part {
  id?: string;
  part_name: string;
  part_number: string;
  manufacturer: string;
  suppliers: Supplier[];
}

interface Supplier {
  supplier: string;
  price: string;
  lead_time: string;
  url: string;
}

interface CartItem extends Part {
  cartId: string;
  selectedSupplier: Supplier;
  quantity: number;
}

export default function PartsOrdering() {
  const [searchQuery, setSearchQuery] = useState('');
  const [parts, setParts] = useState<Part[]>([]);
  const [cart, setCart] = useState<CartItem[]>([]);
  const [comparison, setComparison] = useState<Record<string, Part[]>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const searchParts = async () => {
    if (!searchQuery.trim()) return;

    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`/api/equipment/parts?part_description=${encodeURIComponent(searchQuery)}`);
      if (!response.ok) {
        throw new Error('Search failed');
      }
      const results = await response.json();
      setParts(results || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to search parts');
      setParts([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // Group parts by part_name for comparison
    const grouped = parts.reduce((acc, part) => {
      if (!acc[part.part_name]) {
        acc[part.part_name] = [];
      }
      acc[part.part_name].push(part);
      return acc;
    }, {} as Record<string, Part[]>);
    setComparison(grouped);
  }, [parts]);

  const addToCart = (part: Part, supplier: Supplier) => {
    const cartId = `${Date.now()}-${Math.random()}`;
    const cartItem: CartItem = {
      ...part,
      cartId,
      selectedSupplier: supplier,
      quantity: 1
    };
    setCart([...cart, cartItem]);
  };

  const removeFromCart = (cartId: string) => {
    setCart(cart.filter(item => item.cartId !== cartId));
  };

  const updateQuantity = (cartId: string, quantity: number) => {
    if (quantity < 1) {
      removeFromCart(cartId);
    } else {
      setCart(cart.map(item =>
        item.cartId === cartId ? { ...item, quantity } : item
      ));
    }
  };

  const clearCart = () => {
    setCart([]);
  };

  const calculateTotal = (): number => {
    return cart.reduce((sum, item) => {
      const price = parseFloat(item.selectedSupplier.price.replace(/[R,]/g, '') || '0');
      return sum + (price * item.quantity);
    }, 0);
  };

  const handleCheckout = async () => {
    if (cart.length === 0) {
      alert('Cart is empty');
      return;
    }

    try {
      const orderItems = cart.map(item => ({
        part_name: item.part_name,
        part_number: item.part_number,
        manufacturer: item.manufacturer,
        supplier: item.selectedSupplier.supplier,
        quantity: item.quantity,
        unit_price: item.selectedSupplier.price
      }));

      const response = await fetch('/api/parts-orders/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          items: orderItems,
          total_amount: `R${calculateTotal().toFixed(2)}`,
          technician_id: 'TECH-001', // TODO: get from context
          site_id: 'S002', // TODO: get from context
          status: 'pending_approval'
        })
      });

      if (!response.ok) {
        throw new Error('Failed to create order');
      }

      alert('Order created successfully!');
      clearCart();
      setParts([]);
      setSearchQuery('');
    } catch (err) {
      alert(`Error: ${err instanceof Error ? err.message : 'Failed to create order'}`);
    }
  };

  return (
    <div className="flex flex-col h-full bg-gray-50">
      {/* Search Section */}
      <div className="p-4 bg-white border-b sticky top-0 z-10">
        <h2 className="text-xl font-semibold mb-4">Parts Ordering</h2>
        <div className="flex gap-2">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && searchParts()}
              placeholder="Search parts by name or number..."
              className="w-full pl-10 pr-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              disabled={loading}
            />
          </div>
          <button
            onClick={searchParts}
            disabled={loading}
            className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400"
          >
            {loading ? 'Searching...' : 'Search'}
          </button>
        </div>
        {error && (
          <div className="mt-2 text-sm text-red-600">
            <AlertTriangle className="inline w-4 h-4 mr-1" />
            {error}
          </div>
        )}
      </div>

      <div className="flex flex-1 gap-4 overflow-hidden">
        {/* Comparison Table */}
        <div className="flex-1 overflow-y-auto p-4">
          {Object.entries(comparison).length === 0 && !loading && (
            <div className="text-center text-gray-500 py-8">
              {searchQuery ? 'No parts found' : 'Search for parts to begin'}
            </div>
          )}

          {Object.entries(comparison).map(([partName, variants]) => (
            <div key={partName} className="mb-6 bg-white rounded-lg shadow overflow-hidden">
              <div className="bg-gray-50 px-4 py-3 border-b">
                <h3 className="font-semibold">{partName}</h3>
                {variants.length > 0 && (
                  <p className="text-sm text-gray-600">
                    OEM: {variants[0].part_number} ({variants[0].manufacturer})
                  </p>
                )}
              </div>

              <table className="w-full text-sm">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-2 text-left">Supplier</th>
                    <th className="px-4 py-2 text-left">Price</th>
                    <th className="px-4 py-2 text-left">Lead Time</th>
                    <th className="px-4 py-2 text-left">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {variants.map((variant) =>
                    variant.suppliers.map((supplier) => (
                      <tr key={`${variant.id || variant.part_number}-${supplier.supplier}`} className="border-t hover:bg-gray-50">
                        <td className="px-4 py-2">{supplier.supplier}</td>
                        <td className="px-4 py-2 font-medium">{supplier.price}</td>
                        <td className="px-4 py-2">
                          <span className={`px-2 py-1 rounded text-xs ${
                            supplier.lead_time === 'In stock' ? 'bg-green-100 text-green-700' :
                            'bg-yellow-100 text-yellow-700'
                          }`}>
                            {supplier.lead_time}
                          </span>
                        </td>
                        <td className="px-4 py-2">
                          <button
                            onClick={() => addToCart(variant, supplier)}
                            className="px-3 py-1 bg-blue-600 text-white rounded text-xs hover:bg-blue-700"
                          >
                            Add to Order
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>

              {/* Generic Alternative Notice */}
              {variants.length > 1 && (
                <div className="bg-blue-50 px-4 py-2 text-xs text-blue-700">
                  💡 Generic equivalents available - see pricing above
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Shopping Cart */}
        <div className="w-80 bg-white border-l border-gray-200 overflow-y-auto">
          <div className="sticky top-0 bg-white border-b p-4">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold flex items-center gap-2">
                <ShoppingCart className="w-5 h-5" />
                Cart ({cart.length})
              </h3>
              {cart.length > 0 && (
                <button
                  onClick={clearCart}
                  className="text-blue-600 hover:text-blue-700 text-sm font-medium"
                >
                  Clear
                </button>
              )}
            </div>

            {cart.length > 0 && (
              <div className="text-lg font-bold text-green-600">
                Total: R{calculateTotal().toFixed(2)}
              </div>
            )}
          </div>

          {cart.length === 0 ? (
            <p className="text-center text-gray-400 py-8">No parts in cart</p>
          ) : (
            <div className="space-y-3 p-4">
              {cart.map((item) => (
                <div key={item.cartId} className="bg-gray-50 rounded-lg p-3 border">
                  <div className="flex justify-between items-start mb-2">
                    <div className="flex-1">
                      <p className="font-medium text-sm">{item.part_name}</p>
                      <p className="text-xs text-gray-600">{item.part_number}</p>
                      <p className="text-xs text-blue-600 mt-1">{item.selectedSupplier.supplier}</p>
                    </div>
                    <button
                      onClick={() => removeFromCart(item.cartId)}
                      className="text-red-600 hover:text-red-700 text-sm ml-2"
                    >
                      ✕
                    </button>
                  </div>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => updateQuantity(item.cartId, item.quantity - 1)}
                        className="px-2 py-1 bg-gray-200 rounded text-xs hover:bg-gray-300"
                      >
                        -
                      </button>
                      <input
                        type="number"
                        min="1"
                        value={item.quantity}
                        onChange={(e) => updateQuantity(item.cartId, parseInt(e.target.value) || 1)}
                        className="w-10 text-center text-xs border rounded py-1"
                      />
                      <button
                        onClick={() => updateQuantity(item.cartId, item.quantity + 1)}
                        className="px-2 py-1 bg-gray-200 rounded text-xs hover:bg-gray-300"
                      >
                        +
                      </button>
                    </div>
                    <p className="text-sm font-medium">
                      {item.selectedSupplier.price}
                    </p>
                  </div>
                </div>
              ))}

              <div className="border-t pt-4 mt-4">
                <button
                  onClick={handleCheckout}
                  className="w-full py-3 bg-green-600 text-white rounded-lg hover:bg-green-700 font-semibold flex items-center justify-center gap-2"
                >
                  <Check className="w-5 h-5" />
                  Proceed to Checkout
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
